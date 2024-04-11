
# UnrealRemoteControlWrapper

A (work in progress) python 3 wrapper around Unreal [remote control api](https://docs.unrealengine.com/4.27/en-US/ProductionPipelines/ScriptingAndAutomation/WebControl/QuickStart/). It allows to control Unreal engine remotly, from a dcc ( maya, blender, houdini, etc. ), or a webapp, or any other sources, using a simple python api.

It also provide a wrapper around the python remote execution option you can find in the python plugin settings in Unreal.
This allow you to execute python code from a different python process by sending commands, file path, or python code as string.

upyrc is available on pip:
```
python -m pip install upyrc
```

## Python remote execution (upyre)

This module allows a user to execute python code remotely on a unreal engine session.
It needs to have the python plugin enabled on unreal, as well as the -allow python remote execution- option set on.

In order to create a connection, we need to fetch the settings of the python plugin, this can be done by giving the full path to a uproject to the create config object:

```python
from upyrc import upyre
config = upyre.RemoteExecutionConfig.from_uproject_path(r"D:\Projects\SandBox53\SandBox53.uproject")
```

You can also create the config manually with the right values, such as multicast_group ip and port, multicast_bind_adress or ip_muticast_ttl.
Those values can be found in the project settings of the python plugin.
config = upyre.RemoteExecutionConfig(mutlicast_group=("239.0.0.1", 6766), multicast_bind_adress="0.0.0.0")

To open a connection, you have to use PythonRemoteConnection object, it can be used as context manager like this:

```python
with upyre.PythonRemoteConnection(config) as conn:
    result = conn.execute_python_command("unreal.log('hello form python !')", exec_type=upyre.ExecTypes.EXECUTE_FILE, raise_exc=True)
    print(result)
```

Or you can call open_connection() and close_connection() manually when needed.

```python
conn = upyre.PythonRemoteConnection(config) 
conn.open_connection()
# do commands here
conn.close_connection()
```
To check help on exec_types, you can call help(ExecTypes). Help is available on other objects as well.

Code template are available as jinja files, they can be directly used using helper functions, to execute utility blueprints, set variables, or print logs. For more infos, check test_remote_exection_templates.py.

## Python remote control (uprc, HTTP api):

It needs to have the remote API plugin installed on your Unreal project, as well as the server started, you can do that on the cmd: 

```
WebControl.StartServer
WebControl.EnableServerOnStartup
```
By default, the script use these values bellow as host and port, it matches the default value of the remote plugin from Unreal install, it needs to be set to your values if needed:

```
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 30010
```

Http api [endpoints documentation](https://docs.unrealengine.com/4.27/en-US/ProductionPipelines/ScriptingAndAutomation/WebControl/Endpoints/).

##### Features

> ✔️ Get remote UObject by path.
>
> ✔️ Run query with various filter (class, path, package etc.) to get UObjects.
>
> ✔️ Get / Set UObject properties.
>
> ✔️ Run UObject functions.
>
> ✔️ Get remote blueprint actor and run functions.
>
> ✔️ Get remote presets.
>
> ✔️ Get / Set remote preset properties, functions, actors.
>
> ✔️ Get utilities EditorActorSubsystem and EditorAssetLibrary.
>
> ❌ Batch process is not supported at the moment, Unreal crashes when a batch call is executed.
>
> ❌ Get thumbnail not supported.

##### Basic usage

```python

# Default host and port used by the api:
upyrc.DEFAULT_HOST = "127.0.0.1"
upyrc.DEFAULT_PORT = 30010

# Init the connection
conn = upyrc.URConnection()
print("Ping: ", conn.ping())
# >>> Ping: 0:00:00.015211

# Get Remote UObject by path:
chair_path = "/Game/Maps/TestMap.TestMap:PersistentLevel.StaticMeshActor_2"
robj_chair = conn.get_uobject(chair_path)
print("RUObject: " + str(robj_chair))
# >>> RUObject: UObject: /Game/Maps/TestMap.TestMap:PersistentLevel.StaticMeshActor_2, of Class /Script/Engine.StaticMeshActor

# Access property directly on URemoteObject object:
auto_lod_generation = robj_chair.bEnableAutoLODGeneration
# Set property the same way:
robj_chair.bEnableAutoLODGeneration = True

# dir() returns all properties and functions available remotly.
print(dir(robj_chair))
# >>> ['ActorHasTag (function)', 'AddActorLocalOffset (function)', 'AddActorLocalRotation (function)', 'AddActorLocalTransform (function)',  ... 'bRelevantForLevelBounds (property)', 'bRelevantForNetworkReplays (property)', 'bStaticMeshReplicateMovement (property)']

# You can also load a blueprint actor.
blueprint_path = "/Game/Maps/TestMap.TestMap:PersistentLevel.BUA_TestBlueprint_C_1"
blueprint = conn.get_uobject(blueprint_path)
print("Blueprint: ", blueprint)
# >>> UObject: /Game/Maps/TestMap.TestMap:PersistentLevel.BUA_TestBlueprint_C_1, of Class /Game/Blueprints/BUA_TestBlueprint.BUA_TestBlueprint_C

# And a function with argument(s) too and a return value:
function_result = blueprint.run_function("SimpleTestFuncArgs", MyString="Hello from python !")
print("Function result: ", function_result)
# ---> In Unreal: LogBlueprintUserMessages: [BUA_TestBlueprint_C_UAID_D89EF37396CEAA5E01_2120751343] Hello from python !
# >>> Function result: {'OutputData': True, 'MessagePrinted': 'Hello from python !'}

```

##### Infos

More infos on file: [test_uremote.py](test_uremote.py)

As well as help() on objects:
```python
help(upyrc.URConnection)
help(upyrc._URemoteObject)
# etc..
```
##### Contact

🔗 www.cgtoolbox.com

✉️ contact@cgtoolbox.com
