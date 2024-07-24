'''
    Module added to the remote python session (unreal) sys.paths using add_command_json_output_pipe.jinja template if
    upyre.PythonRemoteConnection "open_output_pipe" is set to True or PythonRemoteConnection.init_json_output_pipe() is called.

    This module allows to write out data to a temporary json file in order to be able to read them back from
    the caller session.

    The environment variable "UPYRE_JSON_PIPE_FILE" is used to set up the json file path where the data will be written to.
    It is set or updated using the add_command_json_output_pipe.jinja template as well.

    Once that module is available, the remote python session (unreal) can simple write data using:
    
    from upyre_json_pipe import command_output_pipe
    command_output_pipe.add("EntryName", data)
'''

import json
import os
import tempfile

output_pipe_temp_file = os.environ.get("UPYRE_JSON_PIPE_FILE", tempfile.gettempdir() + "/uepyrc_output_pipe.json")

class CommandOutputPipe():

    def __init__(self, output_pipe_temp_file: str):

        try:
            with open(output_pipe_temp_file, 'r') as f:
                self.__data = json.load(f)
        except:
            self.__data = {}
        
        self._output_pipe_temp_file = output_pipe_temp_file
        dirname = os.path.dirname(str(self._output_pipe_temp_file))
        if not os.path.exists(dirname):
            os.makedirs(dirname)

    def update_temp_file_path(self, output_pipe_temp_file: str):

        self._output_pipe_temp_file = output_pipe_temp_file

    def flush(self):

        self.__data = {}
        try:
            with open(self._output_pipe_temp_file, 'w') as f:
                json.dump(self.__data, f)
        except:
            pass

    def write(self, entry_name, entry_value):
        
        self.__data[entry_name] = entry_value
        try:
            with open(self._output_pipe_temp_file, 'w') as f:
                json.dump(self.__data, f)
        except TypeError:
            str_entry = str(entry_value)
            self.__data[entry_name] = str_entry
            with open(self._output_pipe_temp_file, 'w') as f:
                json.dump(self.__data, f)

    def read(self, entry_name, default=None):
        
        if os.path.exists(self._output_pipe_temp_file):
            with open(self._output_pipe_temp_file, 'r') as f:
                data = json.load(f)
            return data.get(entry_name, default)
        return default

json_pipe = CommandOutputPipe(output_pipe_temp_file)
