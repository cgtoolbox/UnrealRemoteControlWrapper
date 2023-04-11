import datetime
from dataclasses import dataclass
import json
import logging
import requests
from requests.exceptions import HTTPError
import traceback
import typing
from typing import List

# Log settings
_LOG_FORMAT = "[%(filename)s:%(lineno)s][%(asctime)s][%(levelname)s] %(message)s"
logging.basicConfig(format=_LOG_FORMAT)
def set_log_level(level):
    assert level in (logging.DEBUG, logging.INFO, logging.ERROR, logging.CRITICAL),\
           f"Invalid log level: {level}"
    logging.getLogger().setLevel(level)

# Default constants
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 30010
DEFAULT_TIMEOUT = 10.0  # seconds
DEFAULT_USE_PROPERTIES_CACHE = False

# URConnection routes
ROUTE_INFOS        = {"method":"get", "route":"remote/info"}
ROUTE_SEARCH_ASSET = {"method":"put", "route":"remote/search/assets"}
ROUTE_BATCH        = {"method":"put", "route":"remote/batch"}
ROUTE_GET_PRESETS  = {"method":"get", "route":"remote/presets"}
ROUTE_GET_PRESET   = {"method":"get", "route":"remote/preset/${PRESET_NAME}"}

# URObject routes
ROUTE_FUNC_CALL = {"method":"put", "route":"remote/object/call"}
ROUTE_PROPERTY  = {"method":"put", "route":"remote/object/property"}
ROUTE_THUMBNAIL = {"method":"put", "route":"remote/object/thumbnail"}
ROUTE_DESCRIBE  = {"method":"put", "route":"remote/object/describe"}

# URemotePreset routes
ROUTE_PRESET_GET_PROPERTY     = {"method":"get", "route":"remote/preset/${PRESET_NAME}/property/${PROPERTY_NAME}"}
ROUTE_PRESET_SET_PROPERTY     = {"method":"put", "route":"remote/preset/${PRESET_NAME}/property/${PROPERTY_NAME}"}
ROUTE_PRESET_RUN_FUNCTION     = {"method":"put", "route":"remote/preset/${PRESET_NAME}/function/${FUNCTION_NAME}"}
ROUTE_PRESET_GET_METADATA     = {"method":"get", "route":"remote/preset/${PRESET_NAME}/metadata"}
ROUTE_PRESET_SET_METADATA     = {"method":"put", "route":"remote/preset/${PRESET_NAME}/metadata/${METADATA_KEY}"}
ROUTE_PRESET_GET_METADATA_KEY = {"method":"get", "route":"remote/preset/${PRESET_NAME}/metadata/${METADATA_KEY}"}
ROUTE_PRESET_DELETE_METADATA  = {"method":"delete", "route":"remote/preset/${PRESET_NAME}/metadata/${METADATA_KEY}"}

# NOT SUPPORTED ATM, WebControl.EnableExperimentalRoutes = 1 needed in DefaultEngine.ini file.
__ROUTE_EVENT = {"method":"put", "route":"remote/object/event"}

# Util paths
EDITOR_ACTOR_SUBSYSTEM = "/Script/UnrealEd.Default__EditorActorSubsystem"
EDITOR_ASSET_LIBRARY = "/Script/EditorScriptingUtilities.Default__EditorAssetLibrary"

def get_version():
    import upyrc
    return upyrc.__version__

# Exceptions
class URConnectionError(Exception): ...
class URConnectionInvalidMethodError(Exception): ...
class URConnectionRouteNotFoundError(Exception): ...
class URConnectionInvalidRequestError(Exception): ...
class UObjectMethodNotFOund(Exception): ...

# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# URConnection
# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
class URConnection:
    ''' Base URConnection object, to prepare an object to send requests to Unreal from.
        This is also the class needed to instanciate _URemoteObject.

        connection = URConnection()
        remote_obj = connection.get_ruobject(obj_path)

        It needs to have the remote API plugin installed on your Unreal project, as well as the server started, you can do that on the cmd:
        WebControl.StartServer
        WebControl.EnableServerOnStartup
    '''
    
    # Ellipsis used to forced a request's result to be ignored, when queued in a batch context object.
    BATCH_CONTEXT_SKIP_RESULT = ...

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=DEFAULT_TIMEOUT, generate_transaction=True):

        self._timeout = timeout
        self._generate_transaction = generate_transaction
        self._host = host
        self._port = port
        self._adress_root = f"http://{self._host}:{self._port}"

        self._batch_context = None

    # --- Core ---

    def run_request(self, route_infos: dict=None, json: dict=None, timeout: float=None):
        ''' Send a request to UE webserver.
        '''
        if timeout is None:
            timeout = self._timeout

        route = route_infos["route"]
        method = route_infos["method"]

        adress = f"{self._adress_root}/{route}"
        logging.debug(f"Running request: {route_infos}")
        logging.debug(f"  json: {json}")
        try:
            method = getattr(requests, method)
        except AttributeError:
            raise URConnectionInvalidMethodError(f"Method {method} not supported.")
        else:
            if json:
                json["generateTransaction"] = self._generate_transaction

            # Has a batch context, delay the request execution, it will be handled by _URConnectionBatchContext
            if isinstance(self._batch_context, _URConnectionBatchContext):
                self._batch_context._add_request(route_infos, json)
                return self.BATCH_CONTEXT_SKIP_RESULT
            else:
                try:
                    result = method(adress, json=json, timeout=timeout, headers={'Content-Type': 'application/json'})
                except requests.exceptions.ConnectionError:
                    logging.error("No connection could be made to: " + adress)
                    raise URConnectionError("No connection could be made to: " + adress)
                return self.handle_request_result(result)

    def handle_request_result(self, result):
        ''' Get the raw request's result, and try to parse it to json or usable data.
            Return and log proper error message if any.
        '''
        logging.debug(f"Request execution time {result.elapsed}.")

        if result.status_code == 404:
            msg = result.json().get("errorMessage", "Unknown error.")
            logging.error(msg)
            raise URConnectionRouteNotFoundError(msg)
        
        if result.status_code == 200:
            if result.content == b'': return None
            try:
                r = result.json()
                r["__request_time_elapsed"] = result.elapsed
                return r
            except json.JSONDecodeError:
                return result.content

        msg = result.json().get("errorMessage", "Unknown error.")
        logging.error(msg)
        raise URConnectionInvalidRequestError(msg)

    def batch_context(self):
        ''' Used to create a batch python context object, where all the call made within that context will be queued.
            Once the context.execute() is called, all the result will be run in a single batch on the web server.

            See _URConnectionBatchContext for more infos.
        '''
        return _URConnectionBatchContext(connection=self)

    def infos(self, timeout=None):
        ''' Return webserver infos, all the calls possible and their parameters. 
        '''
        infos = self.run_request(route_infos=ROUTE_INFOS, timeout=timeout)
        return infos

    def ping(self, timeout: float=5.0) -> datetime.timedelta:
        ''' Simple ping the server, return a timedelta, or None in case of failure. 
        '''
        try:
            return self.infos(timeout=timeout)["__request_time_elapsed"]
        except (URConnectionRouteNotFoundError, URConnectionInvalidRequestError, URConnectionError) as e:
            logging.debug("Ping failed: " + str(e))
            return None

    # --- Getters ---

    def query(self, query: str="", package_names: List[str]=[], class_names: List[str]=[], package_paths: List[str]=[], recursive_classe_exlusion_set: List[str]=[],
                    recursive_path: bool=False, recursive_classes: bool=False):
        ''' Query an Asset in the registry according to filters:

            query: The text you want to match in an asset's name. Leaving this field an empty string returns all results.
            package_names: Restricts the search to exact matches of the specified packages. The format of the value is an array of strings, such as ["/Game/MyFolder/MyAsset"].
            class_names: Restricts the search to exact matches of the specified class names. The format of the value is an array of strings.
            package_paths: Restricts the search to any packages that contain the specified paths. For example, ["/Game/MyFolder"] will only return assets with "/Game/MyFolder" in their asset path. The format of the value is an array of strings.
            recursive_classe_exlusion_set: When searching for matching classes recursively, you can specify any classes you want to exclude from the results. The format of the value is an array of strings.
            recursive_path: A boolean specifying whether to search subfolders of the paths specified in PackagePaths.
            recursive_classes: A boolean specifying whether to look at subclasses of classes specified in ClassNames. 
        '''

        query_filter = {
                "PackageNames":package_names,
                "ClassNames": class_names,
                "PackagePaths": package_paths,
                "RecursiveClassesExclusionSet": recursive_classe_exlusion_set,
                "RecursivePaths": recursive_path,
                "RecursiveClasses": recursive_classes
                }
        body = {"Query":query, "Filter":query_filter}
        result = self.run_request(route_infos=ROUTE_SEARCH_ASSET, json=body)
        if not result: return []
        return result["Assets"]

    def get_ruobject(self, path: str, timeout: float= None, use_properties_cache=DEFAULT_USE_PROPERTIES_CACHE):
        ''' Mandatory function to run to create an _URemoteObject object, from its path.
            See _URemoteObject for more infos.
        '''
        body = {"objectPath": path, "access":"READ_ACCESS"}
        try:
            properties = self.run_request(route_infos=ROUTE_PROPERTY, json=body, timeout=timeout)
        except URConnectionInvalidRequestError as e:
            return None

        try:
            body = {"objectPath": path}
            describe = self.run_request(route_infos=ROUTE_DESCRIBE, json=body, timeout=timeout)
        except URConnectionInvalidRequestError as e:
            return None

        describe["properties"] = properties
        return _URemoteObject(path=path, connection=self, describe=describe, use_properties_cache=use_properties_cache, _allow_create=True)

    def get_preset(self, preset_name: str, timeout: float=None):
        ''' Mandatory function to run to create an _URemotePreset object, from its name.
            See _URemotePreset for more infos.
        '''
        route_infos = ROUTE_GET_PRESET.copy()
        route_infos["route"] = route_infos["route"].replace("${PRESET_NAME}", preset_name)
        try:
            preset_infos = self.run_request(route_infos=route_infos, timeout=timeout)
        except URConnectionRouteNotFoundError as e:
            return None

        preset_infos = preset_infos["Preset"]
        return _URemotePreset(path=preset_infos["Path"], connection=self, describe=preset_infos, use_properties_cache=False, _allow_create=True)

    def get_all_presets(self, timeout: float= None) -> List:
        ''' Get all remote preset name and paths.
        '''
        result = self.run_request(route_infos=ROUTE_GET_PRESETS, timeout=timeout)
        if result:
            return result["Presets"]
        return

    def get_thumbnail(self, asset_path='') -> dict:
        ''' Get an thumbnail image from an asset path. 
        '''
        assert asset_path != '', "Invalid asset path."
        body = {"objectPath":asset_path}
        try:
            return self.run_request(route_infos=ROUTE_THUMBNAIL, json=body, timeout=self._timeout)
        except URConnectionRouteNotFoundError:
            return None
    
    def get_editor_actor_library(self):
        ''' Get the EditorActorSubsystem, more infos:
            https://docs.unrealengine.com/5.0/en-US/PythonAPI/class/EditorActorSubsystem.html
        '''
        return self.get_ruobject(EDITOR_ACTOR_SUBSYSTEM)

    def get_editor_asset_library(self):
        ''' Get the EditorAssetLibrary, more infos:
            https://docs.unrealengine.com/4.27/en-US/PythonAPI/class/EditorAssetLibrary.html
        '''
        return self.get_ruobject(EDITOR_ASSET_LIBRARY)

@dataclass
class BatchResult:

    request_id: int
    response_code: int
    response_body: dict

class _URConnectionBatchContext:
    ''' Python context object, used to queue all the requests and execute them with .execute()
        in one batch call.
    '''
    def __init__(self, connection:URConnection = None, timeout:int = 60):
        
        self._connection = connection
        self._context_timeout = timeout
        self._requests = []

    def __enter__(self):
        self._connection._batch_context = self
        return self

    def __exit__(self, ex_type, ex_value, ex_traceback):
        self._connection._batch_context = None

    def _add_request(self, route_infos={}, body={}):
        ''' Called at a request execution, instead of running it, add it to the batch queue.
        '''
        if "generateTransaction" in body:
            del body["generateTransaction"]

        req = {}
        req["RequestId"] = len(self._requests) + 1
        req["URL"] = '/' + route_infos["route"]
        req["Verb"] = route_infos["method"].upper()
        req["Body"] = body

        self._requests.append(req)

    def execute(self) -> list[BatchResult]:
        ''' Execute all requests saved in contect's queue, in one batch request.
            Return an array of BatchResult, with each individual request's result.
        '''
        adress = f"{self._connection._adress_root}/{ROUTE_BATCH['route']}"
        batch_body = {"Requests":self._requests}
        method = getattr(requests, ROUTE_BATCH["method"])

        logging.info(f"Executing {len(self._requests)} requests in batch.")
        with open("D:/batch_context_body.json", 'w') as f:
            json.dump(batch_body, f, indent=4)

        batch_result = method(adress, json=batch_body, timeout=self._context_timeout)
        result = self._connection.handle_request_result(batch_result)
        
        out_data = []
        for response in result["Responses"]:
            out_data.append(BatchResult(response["RequestId"],
                                        response["ResponseCode"],
                                        response["ResponseBody"]))
        return out_data

# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# _URemoteObject
# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

class _URemoteObjectCacheContext:
    ''' Context object to disable / enable _URemoteObject use_properties_cache property. 
    '''
    def __init__(self, uobject=None, use_cache=True):

        self._uobject = uobject
        self._use_cache = use_cache
        self._existing_use_cache = uobject._use_properties_cache

    def __enter__(self):
        self._uobject._use_properties_cache = self._use_cache

    def __exit__(self, ex_type, ex_value, ex_traceback):
        self._uobject._use_properties_cache = self._existing_use_cache

class _URemoteObject:
    ''' Base object to access UObject properties and function remotely.

        -> This class can not be instanciated, the user must use URConnection.get_object(path:str) to get a new instance.

        All _URemoteObject uses an internal cache for properties and functions informations, fetched from the UObject in Unreal.
        All properties can be access normally, as uobejct.my_property (get and set).

        Be default, the properties cache is disabled (see DEFAULT_USE_PROPERTIES_CACHE const). So each time you get a properties or a function info, a new requests will be sent to Unreal.
        If the properties cache is in place, then the property values / functions infos will be fetch from an internal class's cache (similar to __dict__).
        In case of property, if the property is not found in the cache, a requests is made anyway.

        The cache behaviour can be changed in multiple ways, such as:

            - On class instantiation:
                        URConnection.get_object(path, use_properties_cache=True)

            - On class instance:
                        uobject.set_use_properties_cache(True)

            - With a context object, from the class instance:
                        with uobject.properties_cache_context(use_cache=True):
                            print(uobject.my_property)
    '''

    def __new__(cls, *args, **kwargs):
        if not kwargs.get("_allow_create"):
            raise Exception("_URemoteObject can't be instanciated, use URConnection.get_object instead.")
        return object.__new__(cls)

    def __init__(self, path: str='', connection: URConnection=None, describe: dict=None, use_properties_cache=False, **kwargs):
        
        self._use_properties_cache = use_properties_cache
        self._properties_cache = {}

        self._timeout = connection._timeout
        self._connection = connection
        self._name = describe.get("Name")
        self._uclass = describe.get("Class")
        self._functions = self._init_func_dict(describe)
        self._path = path

        self._properties_cache.update(self._init_property_list(describe))

    def __dir__(self) -> list[str]:

        attrs = list(self.__dict__.keys()) + \
                [s + " (function)" for s in list(self._functions.keys())] + \
                [s + " (property)" for s in list(self._properties_cache.keys())]
        return attrs

    def __getattr__(self, name):
        ''' Custom get attribute, for normal properties, the object tries first a requests to the remote object.
            Unless _use_properties_cache is True, then it's fetched from the internal cache directly. 
        '''
        # Handle dunners
        if(name.startswith("__") and name.endswith("__")):
            return super().__getattribute__(name)

        # Check on the cache if needed.
        if super().__getattribute__("_use_properties_cache"):
            try:
                return super().__getattribute__("_properties_cache")[name]
            except KeyError:
                pass
        
        # Run an actual request to get the property from the object in unreal.
        try:
            r = self.get_property(name)
        except URConnectionInvalidRequestError:
            raise AttributeError(name)
        else:
            self._properties_cache[name] = r
            return r

    def __setattr__(self, name, value):
        ''' Custom set attribute, for property not in the current object's built-in dict,
            run a request on the remote object to set the property's value.
        '''
        # If it's an internal attrib, set it normally
        if name in self.__dict__ or name.startswith('_'):
            self.__dict__[name] = value

        # Send a set property request
        else:
            r = self.set_property(property_name=name, property_value=value)
            if r and self._use_properties_cache:
                self._properties_cache[name] = value

    def __str__(self) -> str:

        return f"UObject: {self.get_path()}, of Class {self.get_uclass()}"

    def __eq__(self, other) -> bool:

        try:
            return other.get_path() == self.get_path()
        except AttributeError:
            return False

    def __ne__(self, other) -> bool:

        try:
            return other.get_path() != self.get_path()
        except AttributeError:
            return False

    # --- Core ---

    def _init_property_list(self, describe: dict):
        ''' From a raw describe dictionnary, populate the properties internal cache.
        '''
        return describe["properties"]

    def _init_func_dict(self, describe: dict):
        ''' From a raw describe dictionnary, populate the functions internal cache.
        '''
        funcs = {}
        for f in describe.get("Functions", []):
            
            f_name =  f["Name"]
            if f_name.startswith("K2_"):
                f_name = f_name[3:]
                del f["Name"]
            funcs[f_name] = f

        return funcs

    def properties_cache_context(self, use_cache=True):
        ''' Return a python context object, to allow the user to set the use cache to True or False for all calls in this context.
            For instance:

            with uobject.properties_cache_context(use_cache=True):
                print(uobject.my_property)
        '''
        return _URemoteObjectCacheContext(uobject=self, use_cache=use_cache)

    def refresh_cache(self):
        ''' Run again the describe call, to populate propertiy list. 
        '''
        properties = self.get_all_properties()
        self._properties_cache = properties

    def run_request(self, **kwargs):

        return self._connection.run_request(**kwargs)

    def run_function(self, function_name='', timeout=None, **kwargs):
        ''' Run a function accessible on the remote object, by its name. Any args can be passed as keyword args.
            Function from blueprints are accessible as well.
        '''
        if not function_name in self.get_all_functions():
            UObjectMethodNotFOund(function_name)

        if not timeout:
            timeout = self._timeout
        body = {
                "objectPath":self.get_path(), "access":"WRITE_ACCESS",
                "functionName":function_name,
               }

        if kwargs != {}:
            body["parameters"] = kwargs

        r = self.run_request(route_infos=ROUTE_FUNC_CALL, json=body, timeout=timeout)
        if r:
            return r.get("ReturnValue", r)
        return r

    # --- Getters ---

    def get_name(self) -> str:
        ''' Get name of the current UObject.
        '''
        return self._name

    def get_root_path(self) -> str:
        ''' Get the root path of the UObject, without package.
        '''
        return '/'.join(self._path.split('/')[:-1])

    def get_package(self) -> str:
        ''' Get the package of the current UObject, without path.
        '''
        return self._path.split('/')[-1].split(':')[0].split('.')[0]

    def get_full_name(self) -> str:
        ''' Get UObject full name.
        '''
        return self._path.split(':')[-1]

    def get_uclass(self) -> str:
        ''' Get the class of the UObject (as string).
        '''
        return self._uclass

    def get_path(self) -> str:
        ''' Get the full path of the UObject, including root and package.
        '''
        return self._path

    def get_all_functions(self):
        
        return self._functions

    def get_property(self, property_name='', default=None):
        ''' Get a UObject property value by its name.
            It can be access directly as object's property, like: UObject.my_property
        '''
        if self._use_properties_cache:
            if property_name in self._properties_cache:
                return self._properties_cache[property_name]
            return default

        body = {"objectPath":self.get_path(), "access":"READ_ACCESS", "propertyName": property_name}
        try:
            property_result = self.run_request(route_infos=ROUTE_PROPERTY, json=body, timeout=self._timeout)
            
            # Get property run in a batch, so nothing return here.
            if property_result is URConnection.BATCH_CONTEXT_SKIP_RESULT: return None

            return property_result[property_name]

        except URConnectionInvalidRequestError:
            return default

    def get_function_help(self, function_name: str='', print_out=True):
        ''' Get a function help, name, description and arguments, from its name.
        '''
        func = self.get_all_functions().get(function_name)
        if not func:
            raise UObjectMethodNotFOund(function_name)

        if print_out:
            print('-' * 64)
            print(f"Function: {function_name}")
            print('-' * 64)
            print(func.get("Description", "No description."))
            print("Arguments:")
            for args in func.get("Arguments", []):
                for k, v in args.items():
                    print(f"\t{k}: \t\t{v}")
                print(' ')
            print('-' * 64)

        return func

    def get_all_properties(self):
        ''' Return all object property's names.
        '''
        if self._use_properties_cache:
            if self._properties_cache != {}:
                return self._properties_cache.copy()

        body = {"objectPath":self.get_path(), "access":"READ_ACCESS"}
        all_properties = self.run_request(route_infos=ROUTE_PROPERTY, json=body, timeout=self._timeout)
        if self._use_properties_cache:
            self._properties_cache.update(all_properties)
        return all_properties

    # --- Setters ---

    def set_use_properties_cache(self, use_cache: bool, refresh_cache: bool=True):
        ''' Manually enable / disable cache system on the current object.
        '''
        self._use_properties_cache = use_cache
        if use_cache and (refresh_cache or self._cache_properties == {}):
            self.refresh_cache()
    
    def set_property(self, property_name: str='', property_value=None, timeout: float=None):
        ''' Set a property value from its name and a value.
        '''
        if not timeout:
            timeout = self._timeout
        body = {
                "objectPath":self.get_path(), "access":"WRITE_ACCESS",
                "propertyName":property_name,
                "propertyValue":{property_name:property_value}
               }
        r = self.run_request(route_infos=ROUTE_PROPERTY, json=body, timeout=timeout)
        if r is URConnection.BATCH_CONTEXT_SKIP_RESULT: return None

        if r and r.status_code == 200:
            self._properties_cache[property_name] = property_value
            return property_value
        return False

    # --- Misc ---

    def has_property(self, property_name: str='') -> bool:
        ''' Return True or False if a property with the given name is found on the object.
        '''
        if self._use_properties_cache:
            property_found = property_name in self.__properties_cache
            return property_found
        
        property_found = self.get_property(property_name=property_name)        
        return property_found

    def describe(self):
        ''' Return full description of the remote object, used to populate properties and function lists.
        '''
        body = {"objectPath": self.get_path()}
        return self._connection.run_request(route_infos=ROUTE_DESCRIBE, json=body, timeout=self._timeout)

    def flush_cache(self):
        ''' Flush the internal cache of the RUObject.
        '''
        self._use_properties_cache = False
        self._properties_cache = {}

# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# _URemotePreset
# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

@dataclass(eq=False)
class _URemotePresetProperty:
    ''' Data class to represent a property fetch from a preset. Can be used to set and eval its value. 
    '''
    ID: str
    display_name: str
    underlying_property: dict
    metadata: dict
    owners: list
    preset_name: str
    group: str
    connection: URConnection

    def __eq__(self, other):
        return other.ID == self.ID

    def __str__(self):
        return f"_URemotePresetProperty: {self.display_name} (preset: {self.preset_name})"

    def eval(self):
        ''' Get the property value.
        '''
        route_infos = ROUTE_PRESET_GET_PROPERTY.copy()
        route_infos["route"] = route_infos["route"].replace("${PRESET_NAME}", self.preset_name)\
                                                   .replace("${PROPERTY_NAME}", self.display_name)
        result = self.connection.run_request(route_infos=route_infos)
        if result:
            return result["PropertyValues"][0]["PropertyValue"]
        return None

    def set(self, **kwargs):
        ''' Set the property value.
        '''
        assert kwargs != {}, "Invalid parameters"
        route_infos = ROUTE_PRESET_SET_PROPERTY.copy()
        route_infos["route"] = route_infos["route"].replace("${PRESET_NAME}", self.preset_name)\
                                                   .replace("${PROPERTY_NAME}", self.display_name)
        body = {"PropertyValue": kwargs}
        result = self.connection.run_request(route_infos=route_infos, json=body)

@dataclass(eq=False)
class _URemotePresetFunction:
    ''' Dataclass to represent a function exposed in a preset, can be executed by using the method .run()
    '''
    ID: str
    display_name: str
    underlying_function: dict
    owners: list
    preset_name: str
    group: str
    connection: URConnection

    def __eq__(self, other):
        return other.ID == self.ID

    def __str__(self):
        return f"_URemotePresetFunction: {self.display_name} (preset: {self.preset_name})"

    def run(self, **kwargs):
        
        route_infos = ROUTE_PRESET_RUN_FUNCTION.copy()
        route_infos["route"] = route_infos["route"].replace("${PRESET_NAME}", self.preset_name)\
                                                   .replace("${FUNCTION_NAME}", self.display_name)
        body = {"Parameters":kwargs}
        return self.connection.run_request(route_infos=route_infos, json=body)

@dataclass(eq=False)
class _URemotePresetGroup:
    ''' Dataclass to represent a preset's group, which can contains exposed properties, actors or functions.
    '''
    name: str
    properties: dict
    functions: dict
    actors: dict
    preset_name: str

    def __eq__(self, other):
        return other.name == self.name

    def __str__(self):
        return f"_URemotePresetGroup: {self.name} (preset: {self.preset_name})"

    def get_property(self, property_display_name: str):

        return self.properties.get(property_display_name)

    def get_function(self, function_display_name: str):

        return self.functions.get(function_display_name)

    def get_actor(self, actor_name: str):

        return self.actors.get(actor_name)

@dataclass(eq=False)
class _URemotePresetActor:
    ''' Dataclass to represent an exposed actor in a preset.
    '''
    ID: str
    display_name: str
    underlying_actor: dict
    preset_name: str
    group: str

    def __eq__(self, other):
        return other.ID == self.ID

    def __str__(self):
        return f"_URemotePresetActor: {self.display_name} ({self.actor_path})"

    @property
    def actor_path(self):
        return self.underlying_actor["Path"]

    @property
    def actor_class(self):
        return self.underlying_actor["Class"]

    @property
    def actor_name(self):
        return self.underlying_actor["Name"]

class _URemotePreset(_URemoteObject):
    ''' Represent and Unreal remote preset. You can access properties, functions exposed in the preset, as well as metadata, actors, or groups.
        
        You can get a preset object from a URConnection:
        preset = connection.get_preset(preset_name)

        Or all presets available:
        presets = connection.get_all_presets()

        Unlike the URObject, you can not access properties directly, but with these simple calls:

        preset_property = preset.get_property("property_display_name")
        preset_property.eval()  # To get the value.
        preset_property.set(X=100, Y=10, Z=0)  # To set values.
    '''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._uclass = "_URemotePreset"
        self._groups = self._init_group_list(kwargs["describe"])
        self._actors = self._init_actor_list(kwargs["describe"])

    def __getattr__(self, name):
        return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)

    # --- Internal inits ---
        ''' Internal init function, to init properties, functions and exposed actors dict objects.
        '''
    def _init_property(self, group: str, property_infos: dict) -> _URemotePresetProperty:

        prop = _URemotePresetProperty(property_infos["ID"],
                                      property_infos["DisplayName"],
                                      property_infos["UnderlyingProperty"],
                                      property_infos["Metadata"],
                                      property_infos["OwnerObjects"],
                                      self.get_name(),
                                      group, self._connection)
        return prop

    def _init_function(self, group: str, function_infos: dict) -> _URemotePresetFunction:

        func = _URemotePresetFunction(function_infos["ID"],
                                      function_infos["DisplayName"],
                                      function_infos["UnderlyingFunction"],
                                      function_infos["OwnerObjects"],
                                      self.get_name(),
                                      group, self._connection)
        return func

    def _init_group(self, group_infos: dict) -> _URemotePresetGroup:

        grp_name = group_infos["Name"]
        properties = {prop["DisplayName"]:self._init_property(grp_name, prop) for prop in group_infos.get("ExposedProperties", [])}
        functions = {func["DisplayName"]:self._init_function(grp_name, func) for func in group_infos.get("ExposedFunctions", [])}
        actors = {act["DisplayName"]:self._init_actor(grp_name, act) for act in group_infos.get("ExposedActors", [])}
        grp = _URemotePresetGroup(grp_name, properties, functions, actors, self.get_name())
        return grp

    def _init_actor(self, group: str, actor_infos: dict) -> _URemotePresetActor:

        actor = _URemotePresetActor(actor_infos["ID"],
                                    actor_infos["DisplayName"],
                                    actor_infos["UnderlyingActor"],
                                    self.get_name(),
                                    group)
        return actor

    def _init_group_list(self, describe):

        return {grp["Name"]:self._init_group(grp) for grp in describe.get("Groups", [])}

    def _init_actor_list(self, describe):

        actors = {}
        for grp in describe.get("Groups", []):
            for actor in grp.get("ExposedActors", []):
                actors[actor["DisplayName"]] = self._init_actor(grp["Name"], actor)
        return actors

    def _init_property_list(self, describe):

        properties = {}
        for grp in describe.get("Groups", {}):
            for p in grp.get("ExposedProperties", []):
                prop = self._init_property(grp, p)
                properties[prop.display_name] = prop
        return properties

    def _init_func_dict(self, describe: dict):
        
        funcs = {}
        for grp in describe.get("Groups", []):
            for f in grp.get("ExposedFunctions", []):
                func = self._init_function(grp["Name"], f)
                funcs[func.display_name] = func
        return funcs

    # --- Setter ---

    def set_metadata(self, metadata_key: str, metadata_value: str):
        ''' Set metadata value (str) from its key. If it doesn't exist, it will be created.
        '''
        route_infos = ROUTE_PRESET_SET_METADATA.copy()
        route_infos["route"] = route_infos["route"].replace("${PRESET_NAME}", self.get_name())\
                                                   .replace("${METADATA_KEY}", metadata_key)
        body = {"Value":str(metadata_value)}

        return self.run_request(route_infos=route_infos, json=body, timeout=self._timeout)

    # --- Getter ---

    def get_metadata(self, metadata_key: str=None):
        ''' Get metadata from its key (optional), if no key is set, return the whole metadata dictionary.
        '''
        if not metadata_key:
            route_infos = ROUTE_PRESET_GET_METADATA.copy()
            route_infos["route"] = route_infos["route"].replace("${PRESET_NAME}", self.get_name())
        else:
            route_infos = ROUTE_PRESET_GET_METADATA_KEY.copy()
            route_infos["route"] = route_infos["route"].replace("${PRESET_NAME}", self.get_name())\
                                                    .replace("${METADATA_KEY}", metadata_key)

        result = self.run_request(route_infos=route_infos, timeout=self._timeout)
        if result and metadata_key:
            return result["Value"]
        else:
            return result["Metadata"]

    def get_all_groups(self) -> dict[str, _URemotePresetGroup]:
        ''' Get all groups in the preset, return a list of _URemotePresetGroup.
        '''
        if not self._use_properties_cache:
            self.refresh()
        return self._groups

    def get_group(self, group_name: str) -> _URemotePresetGroup:
        ''' Get a specitic group, according to its name, returns a _URemotePresetGroup.
        '''
        grp = self.get_all_groups().get(group_name)
        return(grp)

    def get_all_actors(self) -> List[_URemotePresetActor]:
        ''' Get all actors exposed to the preset (if any), return a list of _URemotePresetActor.
        '''
        if not self._use_properties_cache:
            self.refresh()
        return self._actors

    def get_actor(self, actor_display_name: str) -> _URemotePresetActor:
        ''' Get a specific exposed actor on this preset, returns a _URemotePresetActor.
        '''
        return self.get_all_actors().get(actor_display_name)

    def get_all_property_names(self) -> list[str]:
        ''' Get all the property names exposed on the preset.
        '''
        if not self._use_properties_cache:
            self.refresh()
        return list(self._properties_cache.keys())

    def get_property(self, property_display_name: str) -> _URemotePresetProperty:
        ''' Get an exposed property on the preset, retuns a _URemotePresetProperty.
            From that object, value can be fetch using .eval(), or set, using .set(value).
        '''
        if not self._use_properties_cache:
            self.refresh()
        return self._properties_cache.get(property_display_name)

    def get_all_function_name(self) -> list[str]:
        ''' Get all exposed function's display name.
        '''
        if not self._use_properties_cache:
            self.refresh()
        return list(self._functions.keys())

    def get_function(self, function_name: str) -> _URemotePresetFunction:
        ''' Get a function exposed on the preset, by display name.
        '''
        if not self._use_properties_cache:
            self.refresh()
        return self._functions.get(function_name)

    # --- Misc ---

    def remove_metadata(self, metadata_key: str):
        ''' Remove a metadata entry from the preset, from its key.
        '''
        route_infos = ROUTE_PRESET_delete_METADATA.copy()
        route_infos["route"] = route_infos["route"].replace("${PRESET_NAME}", self.get_name())\
                                                   .replace("${METADATA_KEY}", metadata_key)

        return self.run_request(route_infos=route_infos, timeout=self._timeout)

    def has_group(self, group_name: str) -> bool:
        ''' Return True if the given group_name is found in the preset's groups.
        '''
        return group_name in list(self.get_groups().keys())

    def refresh(self, timeout: float=DEFAULT_TIMEOUT) -> None:
        '''Run a describe call on the preset again. To repopulate properties and functions as well as groups and actors.
        '''
        route_infos = ROUTE_GET_PRESET.copy()
        route_infos["route"] = route_infos["route"].replace("${PRESET_NAME}", self.get_name())
        describe = self.run_request(route_infos=route_infos, timeout=timeout)["Preset"]
        self._functions = self._init_func_dict(describe)
        self._properties_cache = self._init_property_list(describe)
        self._groups = self._init_group_list(describe)
        self._actors = self._init_actor_list(describe)

