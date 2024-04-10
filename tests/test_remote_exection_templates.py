from upyrc import upyre

# Optional, to have more verbose log
import logging
upyre.set_log_level(logging.DEBUG)

# Set your project path here, it will fetch the python settings of your project, but your MUST have the "Enable remote execution" of the python plugin enabled in unreal.
config = upyre.RemoteExecutionConfig.from_uproject_path(r"D:\Projects\UpyreTest\UpyreTest.uproject")


with upyre.PythonRemoteConnection(config) as conn:

    # Set a property of a utility BP.
    conn.set_bp_property("/Game/Blueprints/BPU_TestUtils.BPU_TestUtils_C", properties={"VarToChange":True})

    # Run utility BP functions.
    conn.execute_bp_method("/Game/Blueprints/BPU_TestUtils.BPU_TestUtils_C", "SimplePrint")
    conn.execute_bp_method("/Game/Blueprints/BPU_TestUtils.BPU_TestUtils_C", "PrintWithArg", args=("Hello", 5), raise_exc=True)

    # Spawn a utility widget BP as tab.
    conn.spawn_utility_widget_bp("/Game/Blueprints/BPW_TestUtilWidget.BPW_TestUtilWidget")

    # Print out some logs.
    conn.log("I'm a message.")
    conn.log_warning("I'm a waaaaarning !")
    conn.log_error("BOUUUH !!!")