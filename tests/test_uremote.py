from upyrc import upyrc
#import logging
#upyrc.set_log_level(logging.DEBUG)
print("Version:", upyrc.get_version())

print("\n----------- INIT CONNECTION --------------------------------------------------------------------------------------------------------------------------------\n")

# Create a connection to Unreal
conn = upyrc.URConnection()
print("Ping: ", conn.ping())
# >>> Ping: 0:00:00.015211

print("\n----------- REMOTE OBJECT --------------------------------------------------------------------------------------------------------------------------------\n")

# Access to object using paths
chair_path = "/Game/Maps/TestMap.TestMap:PersistentLevel.StaticMeshActor_2"

robj_chair = conn.get_ruobject(chair_path)
print("RUObject: " + str(robj_chair))
# >>> RUObject: UObject: /Game/Maps/TestMap.TestMap:PersistentLevel.StaticMeshActor_2, of Class /Script/Engine.StaticMeshActor

# Run a function remotely
folder_path = robj_chair.run_function("GetFolderPath")
print("Folder path: ", folder_path)
# >>> Folder path: TestData

# Access property directly on URemoteObject object:
auto_lod_generation = robj_chair.bEnableAutoLODGeneration
print("bEnableAutoLODGeneration: ", auto_lod_generation)
# >>> bEnableAutoLODGeneration: True

# Access property by name:
auto_lod_generation = robj_chair.get_property("bEnableAutoLODGeneration")
print("bEnableAutoLODGeneration (from func): ", auto_lod_generation)
# >>> bEnableAutoLODGeneration (from func): True

# Set property directly on URemoteObject object:
robj_chair.bEnableAutoLODGeneration = False
print("After set bEnableAutoLODGeneration to False: ", robj_chair.bEnableAutoLODGeneration)
# >>> After set bEnableAutoLODGeneration to False: False

# Set property by name:
robj_chair.set_property("bEnableAutoLODGeneration", True)
print("After set bEnableAutoLODGeneration to True (from func): ", robj_chair.bEnableAutoLODGeneration)
# >>> After set bEnableAutoLODGeneration to True (from func): True

# dir() returns all properties and functions available remotly.
print(dir(robj_chair))
# >>> ['ActorHasTag (function)', 'AddActorLocalOffset (function)', 'AddActorLocalRotation (function)', 'AddActorLocalTransform (function)',  ... 'bRelevantForLevelBounds (property)', 'bRelevantForNetworkReplays (property)', 'bStaticMeshReplicateMovement (property)']

print("\n----------- REMOTE BLUEPRINT --------------------------------------------------------------------------------------------------------------------------------\n")

# You can also load a blueprint actor.
blueprint_path = "/Game/Maps/TestMap.TestMap:PersistentLevel.BUA_TestBlueprint_C_1"
blueprint = conn.get_ruobject(blueprint_path)
print("Blueprint: ", blueprint)
# >>> UObject: /Game/Maps/TestMap.TestMap:PersistentLevel.BUA_TestBlueprint_C_1, of Class /Game/Blueprints/BUA_TestBlueprint.BUA_TestBlueprint_C

# You can run an editor function from the blueprint.
blueprint.run_function("SimpleTestFunc")
# ---> In Unreal: LogBlueprintUserMessages: [BUA_TestBlueprint_C_UAID_D89EF37396CEAA5E01_2120751343] Hello world !

# And a function with argument(s) too and a return value:
function_result = blueprint.run_function("SimpleTestFuncArgs", MyString="Hello from python !")
print("Function result: ", function_result)
# ---> In Unreal: LogBlueprintUserMessages: [BUA_TestBlueprint_C_UAID_D89EF37396CEAA5E01_2120751343] Hello from python !
# >>> Function result: {'OutputData': True, 'MessagePrinted': 'Hello from python !'}

print("\n----------- REMOTE PRESET --------------------------------------------------------------------------------------------------------------------------------\n")

# Get all presets basic infos ( Name, ID and path )
all_presets = conn.get_all_presets()
print("Presets: ", all_presets)
# >>> Presets: [{'Name': 'RCP_TestPreset', 'ID': '916A553549DCE66727D00585DED11589', 'Path': '/Game/RCP_TestPreset.RCP_TestPreset'}]

# Get an preset object, by name.
preset_name = "RCP_TestPreset"
preset = conn.get_preset(preset_name)
print("Preset: ", preset)
# >>> Preset:  UObject: /Game/RCP_TestPreset.RCP_TestPreset, of Class RemotePreset

# Get a preset exposed property:
preset_property = preset.get_property("Relative Location (SM_Lamp_Ceiling)")
print("Relative Location (SM_Lamp_Ceiling) value: ", preset_property.eval())
# >>> Relative Location (SM_Lamp_Ceiling) value: {'X': 330, 'Y': 10, 'Z': 0}

# Set a property value:
preset_property.set(Z=10.0)

# Get a function
preset_function = preset.get_function("My Lib Func (BPF_testFuncLib_C)")
print("Preset function: ", preset_function)
# >>> Preset function:  _URemotePresetFunction: My Lib Func (BPF_testFuncLib_C) (preset: RCP_TestPreset)
preset_function.run()
# ---> In unreal "Hello from lib !"

# Get an exposed actor info, from preset.
preset_exposed_actor = preset.get_actor("SM_TableRound")
print("Exposed actor: ", preset_exposed_actor)
# >>> Exposed actor:  _URemotePresetActor: SM_TableRound (/Game/Maps/TestMap.TestMap:PersistentLevel.StaticMeshActor_6)

print("\n----------- QUERIES --------------------------------------------------------------------------------------------------------------------------------\n")

# Queries the assets registry. Here, get all objects from it. It doesn't return an UObject array, but and array of directionnaries with all the infos found.
all_objects = conn.query()
print("Query all objects: ", all_objects)
# >>> Query all objects: [{'Name': 'BUA_TestBlueprint_C_UAID_D89EF37396CEAA5E01_2120751343', 'Class': '/Game/Blueprints/BUA_TestBlueprint.BUA_TestBlueprint_C', 'Path': '/Game/Maps/MainMap.MainMap:PersistentLevel.BUA_TestBlueprint_C_UAID_D89EF37396CEAA5E01_2120751343', 'Metadata': {'ActorLabel': 'BUA_TestBlueprint'}}, ...]

# You can add filters, here, query only the staticmeshes:
all_static_meshes = conn.query(class_names=["/Script/Engine.StaticMeshActor"])
print("Query all static meshes: ", all_static_meshes)
# >>> Query all static meshes: Query all static meshes:  [{'Name': 'StaticMeshActor_UAID_A4AE111137DC54FB00_1240666663', 'Class': '/Script/Engine.StaticMeshActor', 'Path': '/Game/Maps/MainMap.MainMap:PersistentLevel.StaticMeshActor_UAID_A4AE111137DC54FB00_1240666663', 'Metadata': {'ActorLabel': 'SM_SkySphere'}}, ...]

# To have more infos on the filters that you can apply, check function's help:
help(conn.query)

print("\n----------- UTILITIES --------------------------------------------------------------------------------------------------------------------------------\n")

# Get special utilities, for instance here, actor library, you can check, using dir() what functions are available.
# You can get all the level actor's paths:
actors_library = conn.get_editor_actor_library()
all_level_actors = actors_library.run_function("GetAllLevelActors")
print("All level actors: ", all_level_actors)
# >>> All level actors: ['/Game/Maps/TestMap.TestMap:PersistentLevel.Floor', '/Game/Maps/TestMap.TestMap:PersistentLevel.DirectionalLight_0', ... ]

# You can also get the asset_library utility. As all other UObjects, you can get a function's help:
asset_library = conn.get_editor_asset_library()
asset_library.get_function_help("DeleteDirectory")

'''
print("\n----------- BATCHING PROCESSES --------------------------------------------------------------------------------------------------------------------------------\n")

#/!\ NOT SUPPORTED AT THE MOMENT, UE5 CRASH ON REMOTE BATCH CALLS /!\

chair_path = "/Game/Maps/TestMap.TestMap:PersistentLevel.StaticMeshActor_2"
lamp_path = "/Game/Maps/TestMap.TestMap:PersistentLevel.StaticMeshActor_4"
table_path = "/Game/Maps/TestMap.TestMap:PersistentLevel.StaticMeshActor_6"

robj_chair = conn.get_ruobject(chair_path)
robj_lamp = conn.get_ruobject(lamp_path)
robj_table = conn.get_ruobject(table_path)

with conn.batch_context() as ctx:

    robj_chair.bEnableAutoLODGeneration = False
    robj_lamp.bEnableAutoLODGeneration = False

    results = ctx.execute()

print(results)
'''
