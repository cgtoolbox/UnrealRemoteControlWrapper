from upyrc import upyre

# Optional, to have more verbose log
import logging
upyre.set_log_level(logging.DEBUG)

# Set your project path here, it will fetch the python settings of your project, but your MUST have the "Enable remote execution" of the python plugin enabled in unreal.
config = upyre.RemoteExecutionConfig.from_uproject_path(r"D:\Projects\UpyreTest\UpyreTest.uproject")

# Create the connection
with upyre.PythonRemoteConnection(config) as conn:

    # This execute simple multiline python statement OR file
    result = conn.execute_python_command("unreal.log('Hello')\nunreal.log('World ?')", exec_type=upyre.ExecTypes.EXECUTE_FILE, raise_exc=True)
    print(result)

    # Example with a file path
    result_file = conn.execute_python_command("T:/test_pyfile_ue.py", exec_type=upyre.ExecTypes.EXECUTE_FILE)
    print(result_file)

    # Example with a file path and arguments
    result_file = conn.execute_python_command("T:/test_pyfile_ue.py hello world", exec_type=upyre.ExecTypes.EXECUTE_FILE)
    print(result_file)
    # Here the two arguments "hello" and "world" will be sent to the file before execution. And can be accessed with sys.argv list (the first entry being the file path).

    # You can also evalurate a single line statement and get the result back
    result_statement = conn.execute_python_command("1 + 2", exec_type=upyre.ExecTypes.EVALUATE_STATEMENT)
    print(result_statement.result) # This print 3