import os
import configparser
import uuid
import socket
import logging
import json
from jinja2 import Environment, PackageLoader, FileSystemLoader
from pathlib import Path
from typing import Union, List

'''
This module allows a user to execute python code remotely on a unreal engine session.
It needs to have the python plugin enabled on unreal, as well as the allow python remote execution option set on.

In order to create a connection, we need to fetch the settings of the python plugin, this can be done by giving the full path to a uproject to the create config object:

config = upyre.RemoteExecutionConfig.from_uproject_path(r"D:\Projects\SandBox53\SandBox53.uproject")

You can also create the config manually with the right values, such as multicast_group ip and port, multicast_bind_adress or ip_muticast_ttl.
Those values can be found in the project settings of the python plugin.
config = upyre.RemoteExecutionConfig(mutlicast_group=("239.0.0.1", 6766), multicast_bind_adress="0.0.0.0")

To open a connection, you have to use PythonRemoteConnection object, it can be used as context manager like this:

with upyre.PythonRemoteConnection(config) as conn:
    result = conn.execute_python_command("unreal.log('hello form python !')", exec_type=upyre.ExecTypes.EXECUTE_FILE, raise_exc=True)
    print(result)

Or you can call open_connection() and close_connection() manually when needed.

To check help on exec_types, you can call help(ExecTypes). Help is available on other objects as well.

'''

def get_version():
    import upyrc
    return upyrc.__version__

# Log settings
_LOG_FORMAT = "[%(filename)s:%(lineno)s][%(asctime)s][%(levelname)s] %(message)s"
logging.basicConfig(format=_LOG_FORMAT)
def set_log_level(level):
    assert level in (logging.DEBUG, logging.INFO, logging.ERROR, logging.CRITICAL),\
           f"Invalid log level: {level}"
    logging.getLogger().setLevel(level)

# Constants
UE_MAGIC = "ue_py"
PROTOCOL_VERSION = 1
SOCKET_TIMEOUT = 0.5 # second
PYTHON_SETTING_INI_FILE = "DefaultEngine.ini"
PYTHON_SETTING_ENTRY = "/Script/PythonScriptPlugin.PythonScriptPluginSettings"  # read only in DefaultEngine.ini in projects

# Jinja templates env
jinja_env = Environment(loader=PackageLoader("upyrc", "re_templates"))

# Command ip and port to send commands between python and unreal.
def get_command_address():
    with socket.socket() as s:
        s.bind(('', 0))
        _, port = s.getsockname()
    return ("127.0.0.1", port)

# Config fallbacks from env
UPYRE_BUFFER_SIZE = os.environ.get("UPYRE_BUFFER_SIZE", "2_097_152")
UPYRE_BUFFER_SIZE = int(UPYRE_BUFFER_SIZE)
UPYRE_MULTICAST_GROUP_ADDR = os.environ.get("UPYRE_MULTICAST_GROUP_ADDR", "239.0.0.1")
UPYRE_MULTICAST_GROUP_PORT = os.environ.get("UPYRE_MULTICAST_GROUP_PORT", "6766")
UPYRE_MULTICAST_GROUP_PORT = int(UPYRE_MULTICAST_GROUP_PORT)
UPYRE_MULTICAST_BIND_ADDRESS = os.environ.get("MULTICAST_BIND_ADDRESS", "127.0.0.1")
UPYRE_IP_MULTICAST_TTL = os.environ.get("UPYRE_IP_MULTICAST_TTL", "0")
UPYRE_IP_MULTICAST_TTL = int(UPYRE_IP_MULTICAST_TTL)

# For config fallbacks
BUFFER_SIZE = UPYRE_BUFFER_SIZE
MULTICAST_GROUP = (UPYRE_MULTICAST_GROUP_ADDR, UPYRE_MULTICAST_GROUP_PORT)
MULTICAST_BIND_ADDRESS = UPYRE_MULTICAST_BIND_ADDRESS
IP_MULTICAST_TTL = UPYRE_IP_MULTICAST_TTL

# Python exec types enum
class ExecTypes:
    ''' "ExecuteFile" => Execute the Python command as a file. This allows you to execute either a literal Python script containing multiple statements, or a file with optional arguments.
        "ExecuteStatement" => Execute the Python command as a single statement. This will execute a single statement and print the result. This mode cannot run files.
        "EvaluateStatement" => Evaluate the Python command as a single statement. This will evaluate a single statement and return the result. This mode cannot run files.
    '''
    EXECUTE_FILE = "ExecuteFile"
    EXECUTE_STATEMENT = "ExecuteStatement"
    EVALUATE_STATEMENT = "EvaluateStatement"

# Config exceptions
class InvalidUprojectPathError(Exception): ...
class InvalidConfigError(Exception): ...

# Connection exception
class ConnectionError(Exception): ...

class RemoteExecutionConfig:
    ''' Config used to create connection to unreal. There are 2 ways to create it:

        config = RemoteExecutionConfig(buffer_size=0, multicast_group=(), project_name='TestProject' ...) the user can set it the config manually, if values are not set, this will use the fallback.
        config = RemoteExecutionConfig.from_uproject_path('project_path.uproject'), this will parse the settings found in the project directly.
                                                                                   A full path to a uproject must be given (str).
    '''
    def __init__(self, buffer_size=BUFFER_SIZE, ip_multicast_ttl=IP_MULTICAST_TTL,
                       multicast_group=MULTICAST_GROUP, multicast_bind_address=MULTICAST_BIND_ADDRESS,
                       project_name='', local_uuid=''):

        self.BUFFER_SIZE = buffer_size
        self.MULTICAST_GROUP = multicast_group
        self.MULTICAST_BIND_ADDRESS = multicast_bind_address
        self.IP_MULTICAST_TTL = ip_multicast_ttl

        # Unique indentifier for local process
        if not local_uuid:
            local_uuid = str(uuid.uuid4())
        self.LOCAL_UUID = local_uuid

        # Command ip and port to send commands between python and unreal.
        self.COMMAND_ADDRESS = get_command_address()

        # Optional, project name (without .uproject) will be used to match the right unreal instance if multiple are opened.
        # If not set, the first instance will be used.
        self.PROJECT_NAME = project_name

    def __str__(self) -> str:
        
        return f"Config values: BUFFER_SIZE: {self.BUFFER_SIZE}, MULTICAST_GROUP: {self.MULTICAST_GROUP}, MULTICAST_BIND_ADDRESS: {self.MULTICAST_BIND_ADDRESS}, IP_MULTICAST_TTL: {self.IP_MULTICAST_TTL}, COMMAND_ADDRESS: {self.COMMAND_ADDRESS}, PROJECT_NAME: {self.PROJECT_NAME}"

    @classmethod
    def from_uproject_path(cls, uproject_path: Path):
        ''' Config will be created from 'DefaultEngine.ini' found from the given .uproject path.
            Config's 'project_name' will be automatically set as well.
            If the Python remote execution is not enable, it will raise a InvalidConfigError.
        '''
        uproject_path = Path(uproject_path)
        if not uproject_path.is_file() or not uproject_path.suffix == ".uproject":
            raise InvalidUprojectPathError(str(uproject_path))
        
        unreal_config = uproject_path.parent / "Config" / PYTHON_SETTING_INI_FILE
        if not unreal_config.exists():
            raise InvalidUprojectPathError(f"Can't find: {unreal_config}")
        
        parser = configparser.ConfigParser(strict=False)
        parser.read(unreal_config)

        settings = parser[PYTHON_SETTING_ENTRY]
        remote_execution_enabled = settings.get("bRemoteExecution")
        if not remote_execution_enabled:
            raise InvalidConfigError("Python remote execution not enable in python project settings.")
        
        multicast_group = settings.get("RemoteExecutionMulticastGroupEndpoint")
        if not multicast_group:
            multicast_group = MULTICAST_GROUP
        else:
            multicast_group = (multicast_group.split(':')[0], int(multicast_group.split(':')[1]))

        multicast_bind_address = settings.get("RemoteExecutionMulticastBindAddress", MULTICAST_BIND_ADDRESS)
        ip_multicast_ttl = int(settings.get("RemoteExecutionMulticastTtl", IP_MULTICAST_TTL))
        buffer_size = int(settings.get("RemoteExecutionReceiveBufferSizeBytes", BUFFER_SIZE))

        project_name = uproject_path.name.split('.')[0]

        config = RemoteExecutionConfig(buffer_size=buffer_size, multicast_group=multicast_group,
                                       ip_multicast_ttl=ip_multicast_ttl, multicast_bind_address=multicast_bind_address,
                                       project_name=project_name)
        return config

class _Message:
    ''' Base classe for all message sent to unreal
    '''
    TYPE = ''

    def __init__(self, config: RemoteExecutionConfig):
        self._raw_data = {}
        self.config = config

    def to_data(self):
        return json.dumps(self._raw_data).encode()
    
    def send(self, s: socket.socket):
        ''' Send encoded json data to unreal node.
        '''
        logging.debug(f"Sending message of type '{self.TYPE}'")
        data_msg = self.to_data()
        s.sendto(data_msg, self.config.MULTICAST_GROUP)

    def receive(self, s: socket.socket):
        ''' How the data is reveived needs to be implemented in each message type.
        '''
        raise NotImplementedError()

    def raw_receive(self, s: socket.socket):
        ''' Receive all data from unreal, this might have multiple result (for ping calls for instance).
            It returns an iterator, an it's up to each message type to handle the result properly.
        '''
        data_received = b''
        while 1:
            try:
                data, _ = s.recvfrom(BUFFER_SIZE)
                data_received += data

                try:
                    json_data = json.loads(data_received)
                    data_received = b''
                except json.decoder.JSONDecodeError:
                    continue
                if json_data["type"] == self.TYPE:
                    continue # ignore echo.

                yield json_data

            except socket.timeout:
                break

class PingMessage(_Message):
    ''' Message sent to unreal to find unreal node(s).
    '''
    TYPE = "ping"

    def __init__(self, config: RemoteExecutionConfig):
        super().__init__(config=config)
        self._raw_data = {
                            "version":PROTOCOL_VERSION,
                            "magic":UE_MAGIC,
                            "source":config.LOCAL_UUID,
                            "type":self.TYPE
                         }
        
    def receive(self, s: socket.socket) -> dict:

        for result in self.raw_receive(s):

            # if config has a project name set, we need to be sure to return the right unreal instance with the right project name.
            if self.config.PROJECT_NAME:
                if result["data"]["project_name"] != self.config.PROJECT_NAME:
                    continue
                return result
            
            # if no project name is set, simply send the first result.
            else:
                return result

class OpenConnectionMessage(_Message):
    ''' Message sent to unreal to open a connection to execute command.
        This will create another socket to send command to unreal and receive output.
    '''
    TYPE = "open_connection"

    def __init__(self, unreal_node_id: str, config: RemoteExecutionConfig):
        super().__init__(config=config)
        self._raw_data = {
                            "type":self.TYPE,
                            "version":PROTOCOL_VERSION,
                            "magic":UE_MAGIC,
                            "source":self.config.LOCAL_UUID,
                            "dest":unreal_node_id,
                            "data":{
                                "command_ip":self.config.COMMAND_ADDRESS[0],
                                "command_port":self.config.COMMAND_ADDRESS[1]
                            }
                         }

class CloseConnectionMessage(_Message):
    ''' Close the connection to unreal commands, it needs the unreal node id.
    '''
    TYPE = "close_connection"
    def __init__(self, unreal_node_id: str, config: RemoteExecutionConfig):
        super().__init__(config=config)
        self._raw_data = {
                            "type":self.TYPE,
                            "version":PROTOCOL_VERSION,
                            "magic":UE_MAGIC,
                            "dest":unreal_node_id,
                            "source":self.config.LOCAL_UUID
                         }

class PythonCommandError(Exception): ...

class PythonCommandResult:

    def __init__(self, json_result_data: dict, raise_exc: bool=False):
        ''' json_result_data: the raw json data received from unreal.
            raise_exc: if True and an exception appened during the command execution, it will raise an PythonCommandError exception.
        '''
        self.data = json_result_data.get("data", {})
        self.source_node_id = json_result_data["source"]
        self.target_node_id = json_result_data["dest"]
        self.raise_exc = raise_exc

    def __bool__(self) -> bool:
        return self.success
    
    @property
    def success(self) -> bool:
        success = self.data.get("success", False)
        if not success and self.raise_exc:
            raise PythonCommandError(self.result)
        return success
    
    @property
    def result(self) -> str:
        return self.data.get("result", "None")

    @property
    def output(self) -> list:
        return [o for o in self.data.get("output", [])]
    
    def get_first_output_with_identifier(self, identifier: str) -> str:

        if not identifier.startswith("="): identifier = identifier + "="
        for data in self.output:
            if data.get("output", '').startswith(identifier):
                return data.get("output").replace(identifier, '').strip()

    @property
    def output_str(self) -> str:
        return '\n'.join([o['type'] + ': ' + o['output'] for o in self.output])
    
    def __str__(self):
        if not self.success:
            return self.result
        return self.output_str

class PythonRemoteCommandConnection(_Message):
    ''' Create a connection between unreal and python to execute command on. This needs the unreal node ID fetched by ping message.
    '''
    TYPE = "command"

    def __init__(self, unreal_node_id: str, config: RemoteExecutionConfig):
        super().__init__(config=config)
        self.unreal_node_id = unreal_node_id

        # Create command socket to send and receive data when launching command
        # This is a different socket than the multicast one used to ping and open/close the connection.
        self.cmd_sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.cmd_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.cmd_sock.bind(self.config.COMMAND_ADDRESS)
        self.cmd_sock.settimeout(2.0)
        self.cmd_sock.listen()

        # Connection create with unreal once the message is sent.
        self.cmd_connection, _ = self.cmd_sock.accept()
        self.cmd_connection.settimeout(SOCKET_TIMEOUT)

        self._raw_data = {
                          "type":self.TYPE,
                          "version":PROTOCOL_VERSION,
                          "magic":UE_MAGIC,
                          "source":self.config.LOCAL_UUID,
                          "dest":self.unreal_node_id,
                          "data":{}
                         }
        
    def send(self, command: str, exec_type: ExecTypes=ExecTypes.EVALUATE_STATEMENT, unattended: bool=True, timeout: float=5.0, raise_exc: bool=False) -> PythonCommandResult:
        ''' Send the command, the receive method is executed as well to return the result of the command.
        '''
        logging.debug("Sending command.")
        self._raw_data["data"] = {
                                "command":command,
                                "unattended":unattended,
                                "exec_mode":exec_type
        }
            
        data_msg = self.to_data()
        self.cmd_connection.sendto(data_msg, self.config.COMMAND_ADDRESS)

        return self.receive(timeout=timeout, raise_exc=raise_exc)

    def receive(self, timeout: float=5.0, raise_exc: bool=False) -> PythonCommandResult:
        ''' Get the json result data for the executed command, and construct a CommandResult object with it.
            The implementation is a bit different than other messages as the timeout mechanism can't be used here as we don't know how long the command will take unreal side.
            For safety, we have a different timeout version than other message if there is an issue with getting the command output. It can be set on the execute_python_command function.
        '''

        self.cmd_connection.settimeout(timeout)
        json_data = None
        data_received = b''
        while 1:
            try:
                data, _ = self.cmd_connection.recvfrom(BUFFER_SIZE)
                data_received += data

                try:
                    json_data = json.loads(data_received)
                    data_received = b''
                except json.decoder.JSONDecodeError:
                    continue
                if json_data["type"] == self.TYPE:
                    json_data = None
                    continue # ignore echo.

                # Data is complete and valid at this point
                break

            except socket.timeout:
                break

        logging.debug("Command result received.")
        return PythonCommandResult(json_data, raise_exc=raise_exc)

class PythonRemoteConnection:
    ''' Open a connection to a unreal node (by project name, or by default, the first one found, depending on the config).
        From there you can execute a python command.
        It can be used as context manager, to close the connection once out.
    '''
    def __init__(self, config: RemoteExecutionConfig=None, project_name: str=''):

        if not config:
            config = RemoteExecutionConfig()
        self.config = config
        logging.debug(str(config))

        if project_name:
            self.config.PROJECT_NAME = project_name

        self.connection_created = False
        self.unreal_node_id = ''
        self.remote_command_connection = None
        self.conneciton_infos = None

        # Init the multicast socket, to send messages to unreal (Ping, Open/Close connection).
        self.mcastsock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.mcastsock.settimeout(SOCKET_TIMEOUT)
        self.mcastsock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, IP_MULTICAST_TTL)
        self.mcastsock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        self.mcastsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.mcastsock.bind((self.config.MULTICAST_BIND_ADDRESS, self.config.MULTICAST_GROUP[1]))
        membership_request = socket.inet_aton(self.config.MULTICAST_GROUP[0]) + socket.inet_aton(self.config.MULTICAST_BIND_ADDRESS)
        self.mcastsock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership_request)

    def __enter__(self):
        self.open_connection()
        return self

    @property
    def socket(self):
        return self.mcastsock
    
    def __exit__(self, *args):
        self.close_connection()
    
    def open_connection(self):
        ''' Ping unreal until it finds a node (unreal editor instance running) which matches the target project name, if any, otherwise take the first node found.
            When a node is found, open a connection with it by sending an open_connection message and open a receiver socket here too.
        '''
        ping_message = PingMessage(self.config)
        ping_message.send(self.mcastsock)
        pong_data = ping_message.receive(self.mcastsock)
        if not pong_data:
            raise ConnectionError("Connection failed.")
        self.unreal_node_id = pong_data["source"]
        self.connection_infos = pong_data["data"]

        OpenConnectionMessage(self.unreal_node_id, self.config).send(self.mcastsock)
        self.connection_created = True
        self.remote_command_connection = PythonRemoteCommandConnection(self.unreal_node_id, self.config)
        logging.info(f"Connection established: project {pong_data['data']['project_name']} (unreal {pong_data['data']['engine_version']})")

    def close_connection(self):
        ''' Close the active command connection to unreal node.
        '''
        if self.connection_created or self.unreal_node_id != '':
            CloseConnectionMessage(self.unreal_node_id, self.config).send(self.mcastsock)
            self.connection_infos = None
            self.connection_created = False
            self.unreal_node_id = ''
            self.mcastsock.close()
            logging.debug("Connection closed !")

    def execute_python_command(self, command: str, exec_type: ExecTypes=ExecTypes.EVALUATE_STATEMENT, unattended: bool=True, timeout: float=5.0, raise_exc: bool=False):
        ''' Execute the given python command, this can be either python statement(s) or a path to a python file.
            unattended: Whether to run the command in "unattended" mode (suppressing some UI)
            exec_type: See ExecTypes help.
            timeout: in seconds, defautl is 5. After than timeout, the function result will not be fetched, but it might still be executed on unreal side !
            raise_exc: if True and an exception appened during the command execution, it will raise an PythonCommandError exception.
        '''
        if not self.remote_command_connection:
            raise ConnectionError("Connection was not openned.")
        return self.remote_command_connection.send(command=command, exec_type=exec_type, unattended=unattended, timeout=timeout, raise_exc=raise_exc)
    
    def execute_template_file(self, file_path: Union[Path, str], template_kwargs: dict={},
                              search_paths: List[Union[Path, str]]=[],
                              timeout: float=5.0, raise_exc=True) -> PythonCommandResult:
        ''' Render and execute a given .jinja template file.
            An optionnal list of search paths can be given, to find other inherited templates.
        '''
        
        if isinstance(file_path, str):
            file_path = Path(file_path)

        parent = file_path.parent
        search_paths.append(parent)
        temp_env = Environment(loader=FileSystemLoader([str(s) for s in search_paths]))
        template = temp_env.get_template(file_path.name)
        python_code = template.render(template_kwargs)
        return self.execute_python_command(python_code, exec_type=ExecTypes.EXECUTE_FILE, timeout=timeout, raise_exc=raise_exc)
    
    def execute_template_command(self, template_name: str, timeout: float=5.0, raise_exc: bool=False, exec_type=ExecTypes.EXECUTE_FILE, template_kwargs={}) -> PythonCommandResult:
        ''' Execute a rendered jinja template file, found in re_templates folder.
            'template_kwargs' dicitonnary will be applied to the template.
        '''
        if not template_name.endswith(".jinja"):
            template_name = template_name.split('.')[0] + ".jinja"

        template = jinja_env.get_template(template_name)
        python_code = template.render(template_kwargs)
        return self.execute_python_command(python_code, exec_type=exec_type, timeout=timeout, raise_exc=raise_exc)

    # Helper functions
    
    def log(self, message :str="", raise_exc=True) -> PythonCommandResult:
        return self.execute_template_command("log.jinja", template_kwargs={"msg":message, "level":"message"}, raise_exc=raise_exc)
    
    def log_warning(self, message :str="", raise_exc=True) -> PythonCommandResult:
        return self.execute_template_command("log.jinja", template_kwargs={"msg":message, "level":"warning"}, raise_exc=raise_exc)
    
    def log_error(self, message :str="", raise_exc=True) -> PythonCommandResult:
        return self.execute_template_command("log.jinja", template_kwargs={"msg":message, "level":"error"}, raise_exc=raise_exc)
    
    def execute_bp_method(self, bp_class_path: str="", bp_method_name: str="", args=(), kwargs={}, raise_exc=True) -> PythonCommandResult:
        ''' Execute the template to execute utility BP functions.
        '''
        assert bp_class_path != '', "Invalid bp_class_path."
        assert bp_method_name != '', "Invalid bp_method_name."
        assert bp_class_path.endswith('_C'), "Invalid bp_class_path, must end with '_C'"
        return self.execute_template_command("run_editor_bp_method.jinja",
                                            template_kwargs={"bp_class_path":bp_class_path, "bp_method_name":bp_method_name, "call_method":True, "args":args, "kwargs":kwargs},
                                            raise_exc=raise_exc)
    
    def execute_editor_widget_bp_method(self, bp_path: str="", bp_method_name: str="", args=(), kwargs={}, raise_exc=True) -> PythonCommandResult:
        ''' Execute the template to execute utility BP functions.
        '''
        assert bp_path != '', "Invalid bp_class_path."
        assert bp_method_name != '', "Invalid bp_method_name."
        return self.execute_template_command("run_editor_widget_bp_method.jinja",
                                            template_kwargs={"bp_path":bp_path, "bp_method_name":bp_method_name, "args":args, "kwargs":kwargs},
                                            raise_exc=raise_exc)
    
    def set_bp_property(self, bp_class_path: str="", properties={}, raise_exc=True) -> PythonCommandResult:
        ''' Execute the template to set properties on a utility BP.
        '''
        assert bp_class_path != '', "Invalid bp_class_path."
        assert properties != {}, "Invalid properties."
        assert bp_class_path.endswith('_C'), "Invalid bp_class_path, must end with '_C'"
        return self.execute_template_command("run_editor_bp_method.jinja",
                                             template_kwargs={"bp_class_path":bp_class_path, "properties":properties, "set_properties":True},
                                             raise_exc=raise_exc)

    def spawn_utility_widget_bp(self, widget_path: str="", raise_exc: bool=True) -> PythonCommandResult:
        ''' Take a utility widget BP and spawn it as tab.
        '''
        return self.execute_template_command("spawn_utility_widget_bp.jinja",
                                             template_kwargs={"widget_path":widget_path},
                                             raise_exc=raise_exc)
    
    def close_utility_widget_bp_from_id(self, widget_id: str="", raise_exc: bool=True) -> PythonCommandResult:
        ''' Close a utility widget already spawned.
        '''
        return self.execute_template_command("close_widget_bp_from_id.jinja",
                                             template_kwargs={"widget_id":widget_id},
                                             raise_exc=raise_exc)
    
    def import_fbx_static_meshes(self, fbx_file_paths: List[str], destination_folder_path: str,
                                       combine_meshes: bool=True, raise_exc: bool=True) -> PythonCommandResult:
        ''' Import given fbx file(s) and import them (static meshes only) to the given destination_folder_path.
            The destination_folder_path must starts with /Game/ (Which is the /Content/ of a UE project).

            If multiple meshes are found in the FBX, they can be combined or not, using the combine_meshes bool.
        '''
        return self.execute_template_command("fbx_static_mesh_import.jinja",
                                             template_kwargs={"fbx_file_paths":[f.replace('\\', '/') for f in fbx_file_paths],
                                                              "destination_folder_path":destination_folder_path,
                                                              "combine_meshes":combine_meshes},
                                             raise_exc=raise_exc)
    
    def export_fbx_static_meshes(self, static_mesh_package_names: List[str], destination_folder_path: str,
                                       export_collisions: bool=False, export_level_of_detail: bool=False, export_vertex_color: bool=False,
                                       raise_exc: bool=True) -> PythonCommandResult:
        ''' Export given static mesh(es) from package name (/Game/myfolder/myasset) as fbx in a given folder.
        '''
        return self.execute_template_command("fbx_static_mesh_export.jinja",
                                             template_kwargs={"static_mesh_package_names":static_mesh_package_names,
                                                              "export_collisions":export_collisions,
                                                              "export_level_of_detail":export_level_of_detail,
                                                              "export_vertex_color":export_vertex_color,
                                                              "destination_folder_path":destination_folder_path},
                                             raise_exc=raise_exc)