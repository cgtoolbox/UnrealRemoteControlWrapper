from upyrc import upyre

# Optional, to have more verbose log
import logging
upyre.set_log_level(logging.DEBUG)

PROJECT_FOLDER = "D:/Projects/UpyreTest/UnrealRemoteControlTestData"
# ==> Change it for your test project path.

# Set your project path here, it will fetch the python settings of your project, but your MUST have the "Enable remote execution" of the python plugin enabled in unreal.
config = upyre.RemoteExecutionConfig.from_uproject_path(f"{PROJECT_FOLDER}/UpyreTest.uproject")

# Create the connection
with upyre.PythonRemoteConnection(config, open_json_output_pipe=True) as conn:
    
    # This execute simple multiline python statement OR file
    result = conn.execute_python_command("unreal.log('Hello')\nunreal.log('World ?')", exec_type=upyre.ExecTypes.EXECUTE_FILE, raise_exc=True)
    print(result)

    # Example with a file path
    conn.write("TestRead", 1234)  # Data sent to process using the json temp file pipe.
    result_file = conn.execute_python_command(f"{PROJECT_FOLDER}/Content/Blueprints/test_pyfile_ue.py", exec_type=upyre.ExecTypes.EXECUTE_FILE)
    print(result_file)

    # Example with a file path and arguments
    result_file = conn.execute_python_command(f"{PROJECT_FOLDER}/Content/Blueprints/test_pyfile_ue.py hello world", exec_type=upyre.ExecTypes.EXECUTE_FILE)
    print(result_file)
    # Here the two arguments "hello" and "world" will be sent to the file before execution. And can be accessed with sys.argv list (the first entry being the file path).
    # >>> From cmd arguments: hello world.

    # You can also evalurate a single line statement and get the result back
    result_statement = conn.execute_python_command("1 + 2", exec_type=upyre.ExecTypes.EVALUATE_STATEMENT)
    print(result_statement) # This print 3

    # Set a property of a utility BP.
    conn.set_bp_property("/Game/Blueprints/BPU_TestUtils.BPU_TestUtils_C", properties={"VarToChange":True})

    # Run utility BP functions.
    conn.execute_bp_method("/Game/Blueprints/BPU_TestUtils.BPU_TestUtils_C", "SimplePrint")
    conn.execute_bp_method("/Game/Blueprints/BPU_TestUtils.BPU_TestUtils_C", "PrintWithArg", args=("Hello", 5), raise_exc=True)

    # Spawn a utility widget BP as tab.
    r = conn.spawn_utility_widget_bp("/Game/Blueprints/BPW_TestUtilWidget.BPW_TestUtilWidget")
    # ---> In Unreal the BPW_TestUtilWidget will be spawned in a tab.
    
    # >>> BPW_TestUtilWidget_C /Game/Levels/L_upyrc.L_upyrc:BPW_TestUtilWidget_C_0
    conn.execute_editor_widget_bp_method("/Game/Blueprints/BPW_TestUtilWidget.BPW_TestUtilWidget", "TestFunction", args=("Hello world",))
    # ---> In Unreal, will call method "TestFunction" of the widget spawned, it will print out "Message: Hello world".
    widget_id = conn.read("WidgetID")
    conn.close_utility_widget_bp_from_id(widget_id)

    # Print out some logs.
    conn.log("I'm a message.")
    conn.log_warning("Uho, I'm a warning...")
    conn.log_error("Oh bummer I'm an error !!!")
    # ---> In Unreal: Will print the logs in the "Output log" tab.

    # Execute custom template.
    conn.execute_template_file(f"{PROJECT_FOLDER}/Content/Blueprints/test_template.jinja", template_kwargs={"msg":"Hello !"})
    # ---> In Unreal: Will print "Im printed from a custom template ! Hello ! End of template" in the "Output log" tab.
    