from __future__ import print_function  # python3 style print statements.
import sys
import os
import platform
import inspect
import json
import subprocess

# This is a temporary solution since the file utilities.py was moved, but users may
# have an old copy of the associated pyc file.
oldfile = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'utilities.pyc')
if os.path.exists(oldfile):
    import time
    try:
        os.remove(oldfile)
    except:
        time.sleep(1.000)
        os.remove(oldfile)
    time.sleep(1.000)

sys.path.append(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', '..', 'lib_py', 'python3'))

sys.path.append(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', '..'))
import bom_publish

sys.path.append(
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)), '..', '..',
        'componentcache', 'noarch'))
from componentcache import the_component_cache

from application_specific import app_specific_folders
from application_specific import get_workspace_machine_file_path
from application_specific import get_shared_machine_file_path
from application_specific import get_compilation_roots
from application_specific import app_specific_env
from application_specific import app_specific_sandbox_data
from application_specific import compute_app_specific_path
from application_specific import get_app_specific_bom_file

from helpers import init
from helpers import _check_coded_ui_testbuilder_config
from helpers import _is_valid_variant
from helpers import _get_variant_dir_env_variable
from helpers import _get_scons_variant_dir

from subcommands import subcommand_setup
from subcommands import subcommand_env
import command_line_options

class Data:
    # These four are loaded and persisted
    options = {}
    machine = {}
    network = {}
    artifact = []
    # These four are computed
    local = {}
    env = {}
    env2 = {}  # env2 depends upon environment variables set in env.
    env_linux = {}
    env_linux2 = {}

def main(argv):
    STATUS = 0
    sys.stdout.flush()

    data = Data()
    # This string should be unicode.
    # All future string paths are derived from it.
    data.local['input_tree'] = str(
        os.path.abspath(
            os.path.dirname(inspect.getsourcefile(lambda: 0)) +
            '../../../../').replace("\\", "/"))
    # In the future, if we are to support placing the workspace in a directory with a unicode character in the path, we must upgrade to Python3.
    # Python2 interpeter cannot be invoked, passing the filename of a python script as string which is in a path with a non-ascii codepoint.
    # While it is possible to correct for additional arguments in the body of the script, the first argument holding the python script name is processed
    # by the interpreter internally, and does not support unicode.
    # Also, sys.path only supports type 'str' for python2.

    data = compute_minimal_sandbox_data(data)
    parser = command_line_options.create(data)
    args, subargs = parse_arguments(parser)

    data = load_options_data(data)
    data = process_sandbox_options_args(data, vars(args), parser)

    if vars(args)['func'] != subcommand_setup:
        data = load_remaining_sandbox_data(data, vars(args))
        STATUS = initialize_supporting_scripts(data)
        if STATUS != 0:
            return STATUS

    if os.environ.get('SANDBOX_GENERATE_SETENV') is not None:
        if (vars(args)['func'] != subcommand_setup):
            data.options['force_set_env'] = False
            if vars(args)['func'] == subcommand_env:
                data.options['force_set_env'] = True
            generate_set_env(parser, args, subargs, data)
    else:
        STATUS = execute_subcommand(parser, args, subargs, data)
    return STATUS

def execute_subcommand(parser, args, subargs, data):
    STATUS = args.func(parser, args, subargs, data)
    return STATUS

def parse_arguments(parser):
    # If we exit with non-zero, the first invocation
    # of sandbox.py will terminate the calling batch file.
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    args = {}
    subargs = {}
    try:
        # Any usage error or help request throws here.
        args, subargs = parser.parse_known_args()
    except:
        sys.exit(1)
    return (args, subargs)

def initialize_supporting_scripts(data):
    init(data.options['verbosity'])

    bom_publish.init(data.options['verbosity'], data.local['os_platform'], data.local['intel_compiler_root'])

    artifact_repository_file_list = []
    for location in data.machine['network_location']:
        artifact_repository_file_list.append(os.path.join(
            data.local['sandbox_input_dir'], 'networks',
            'artifact_repository_' + location + '.json'))

    component_bom_file = get_app_specific_bom_file(data)
    STATUS = the_component_cache.initialize(
        bom_file=component_bom_file,
        artifact_repository_file=artifact_repository_file_list,
        target_platform=data.local['platform'],
        component_cache_dir=data.machine['component_cache_root'],
        component_workspace_dir=data.local['output_components_dir'],
        verbosity=data.options['verbosity'])
    return STATUS

def compute_minimal_sandbox_data(data):
    data.local['is_linux'] = False
    data.local['os_platform'] = 'WIN8664'
    data.local['platform'] = 'win64'
    intel_compiler_version = '2019.4.245'
    data.local['intel_compiler_root'] = os.path.join(os.environ.get('ProgramFiles(x86)',''), 'IntelSWTools', 'compilers_and_libraries_' + intel_compiler_version, 'windows')
    if (platform.system() == 'Linux'):
        data.local['is_linux'] = True
        data.local['os_platform'] = 'LX8664_RHE73'
        data.local['platform'] = 'linux64rhe73'
        intel_compiler_version = '2019.4.243'
        data.local['intel_compiler_root'] = os.path.join('/opt', 'intel', 'compilers_and_libraries_' + intel_compiler_version, 'linux')
    # Example intel to scons relation for CDE2020 : '2019.4.245' to '19.0.4.245'
    data.local['intel_compiler_version_scons'] = intel_compiler_version[2:].replace('.', '.0.', 1)
    data.local['sandbox_input_dir'] = data.local['input_tree'] + '/tools/sandbox'  # TODO: Needs to be configurable.
    command = 'git rev-parse --abbrev-ref HEAD'
    branch = subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout.decode("utf-8").strip()
    data.local['output_tree'] = data.local['input_tree'] + '_{}_output'.format(branch)
    print('output_tree:', data.local['output_tree'])
    exit(0)
    if not os.path.isdir(data.local['output_tree']):
        os.makedirs(data.local['output_tree'])
    data.local['sandbox_output_dir'] = data.local['output_tree'] + '/sandbox'
    if not os.path.isdir(data.local['sandbox_output_dir']):
        os.makedirs(data.local['sandbox_output_dir'])
    data.local['previous_options_file'] = data.local[
        'sandbox_output_dir'] + '/previous_options.json'
    data = app_specific_folders(data)
    return data

def load_options_data(data):
    # Seed defaults
    data.options['build_variant'] = data.local['vtune_name']
    data.options['num_jobs'] = '8'
    data.options['num_retries'] = '5'
    data.options['verbosity'] = 0
    # Read previously saved options if available.
    if os.path.isfile(data.local['previous_options_file']):
        with open(data.local['previous_options_file']) as in_file:
            data.options.update(json.load(in_file))
    return data

def process_sandbox_options_args(data, argvars, parser):
    # Each shell window should remember which build option it was using.
    data.options['build_variant'] = os.environ.get('SANDBOX_VARIANT') or data.options['build_variant']
    # Override the previous build variant value if the user explicitly provides one as an argument.
    build_variant = argvars['build_variant']
    if build_variant is not None:
        data.options['build_variant'] = build_variant

    if not _is_valid_variant(data):
        parser.error("invalid build type of '" +
                     data.options['build_variant'] + "' specified.")

    if argvars['jobs'] is not None:
        data.options['num_jobs'] = str(argvars['jobs'])
    if argvars['retries'] is not None:
        data.options['num_retries'] = str(argvars['retries'])
    if argvars['verbosity'] is not None:
        data.options['verbosity'] = argvars['verbosity']

    return data

def load_remaining_sandbox_data(data, argvars):
    data = _read_machine_file(data)
    data = _read_network_file(data, data.machine['network_location'][0])
    data = _read_artifact_files(data)
    data = compute_common_base_dirs(data)
    data = calculate_platform_tools(data)
    data = app_specific_sandbox_data(data)
    data = compute_compiler_paths(data)
    data = compute_library_paths(data)
    data = compute_universal_build_options(data, argvars)
    data = compute_env_data(data)
    data = app_specific_env(data)
    return data

def _read_machine_file(data):
    machine_file_path = get_shared_machine_file_path(data)
    workspace_machine_file_path = get_workspace_machine_file_path(data)
    if os.path.isfile(workspace_machine_file_path):
        machine_file_path = workspace_machine_file_path

    # TODO: check the file exists. If it does not, error out (with a useful message).
    data.local['machine_file'] = machine_file_path
    # TODO: Sanitize the machine file contents. In particular error out (with a useful message) if backslashes exist in the component_cache dir.
    # Read the contents of the machine file.
    data.machine['enable_buildcaching'] = False
    data.machine['enable_multiconfig_ide'] = False
    with open(machine_file_path) as in_file:
        data.machine.update(json.load(in_file))

    # Support single string or list of strings
    locations = data.machine['network_location']
    if type(locations) is not list:
        locations = [data.machine['network_location']]
        data.machine['network_location'] = locations

    return data

def _read_network_file(data, location):
    data.machine['component_cache_root'] = os.path.expanduser(
        data.machine['component_cache_root'])
    network_file_path = data.local[
        'sandbox_input_dir'] + '/networks/' + location + '.json'
    with open(network_file_path) as in_file:
        data.network.update(json.load(in_file))
    return data

def _read_artifact_files(data):
    data.machine['component_cache_root'] = os.path.expanduser(
        data.machine['component_cache_root'])
    artifact_file_path_list = []
    locations = data.machine['network_location']
    for location in locations:
        artifact_file_path_list.append(data.local[
            'sandbox_input_dir'] + '/networks/artifact_repository_' + location + '.json')
    for artifact_file_path in artifact_file_path_list:
        with open(artifact_file_path) as in_file:
            temp = {}
            temp.update(json.load(in_file))
            data.artifact.append(temp)
    return data

def calculate_platform_tools(data):
    SevenZCmd = '7z.exe'
    if data.local['is_linux'] == True:
        SevenZCmd = '7z'
    data.local['7z_cmd'] = SevenZCmd

    data.local['time_cmd'] = data.local[
        'sandbox_input_dir'] + '/implementation/timecmd.bat'

    # The leaf_components_dir variable defines the soft link location to Components.
    data.local['compcache_disabled'] = data.local[
        'leaf_components_dir'] + '/component_caching_disabled.txt'  # TODO: Not really sure where this belongs
    return data

def compute_common_base_dirs(data):
    scons_variant_dir = _get_scons_variant_dir(data)
    data.local['mod_dir'] = scons_variant_dir + '/mod'
    data.local['leaf_dir'] = data.local['mod_dir'] + '/leaf'
    data.local['leaf_components_dir'] = data.local['leaf_dir'] + '/Components'
    data.local['tests_dir'] = scons_variant_dir + '/tests'
    data.local['output_components_dir'] = os.path.join(
        data.local['output_tree'], 'components')
    return data

def compute_env_data(data):
    # Save the current build variant in an environment variable, so each shell
    # instance can maintain a different value.
    data.env['SANDBOX_VARIANT'] = data.options['build_variant']
    variant_dir = _get_variant_dir_env_variable(data)
    data.env['MOD_DIR'] = os.path.join(variant_dir, 'mod')
    data.env['OBJ_DIR'] = os.path.join(variant_dir, 'obj')
    data.env['LEAF_DIR'] = os.path.join(variant_dir, 'mod', 'leaf')
    return data

def compute_universal_build_options(data , argvars):
    data.local['SKIPTESTEXECUTION'] = ''
    isTestExecutionDisabled = 'skip_lockserver_testexecution' in argvars and argvars['skip_lockserver_testexecution'] == True
    if isTestExecutionDisabled == True:
        data.local['SKIPTESTEXECUTION'] = 'True'
    return data

def compute_library_paths(data):
    data.local['gtest_dir'] = os.path.join(data.local['output_tree'],
                                           'components', 'googletest',
                                           data.local['os_platform'])
    data.local['btree_dir'] = os.path.join(data.local['output_tree'],
                                           'components', 'googlebtree')
    data.local['boost_dir'] = os.path.join(data.local['output_tree'],
                                           'components', 'boost',
                                           data.local['os_platform'])
    data.local['hdf5_dir'] = os.path.join(data.local['output_tree'],
                                          'components', 'hdf5',
                                          data.local['os_platform'])
    return data

def compute_compiler_paths(data):
    if data.machine.get('visual_studio_unavailable',
                        False) != True and data.local['is_linux'] == False:
        data.local[
            'vs_dir'] = "%ProgramFiles(x86)%/Microsoft Visual Studio/2017/Professional"
        enterprise_dir = os.path.join(
            os.environ['ProgramFiles(x86)'],
            "Microsoft Visual Studio/2017/Enterprise")
        if os.path.exists(enterprise_dir) and os.path.isdir(enterprise_dir):
            data.local[
                'vs_dir'] = "%ProgramFiles(x86)%/Microsoft Visual Studio/2017/Enterprise"
            _check_coded_ui_testbuilder_config(os.path.join(enterprise_dir, r'Common7/IDE/CodedUITestBuilder.exe.config'))
        data.local['ifort_dir'] = data.local['intel_compiler_root']
        data.local['intelmkl_dir'] = '"' + os.path.join(data.local['ifort_dir'], 'mkl') + '"'
        # Set ifort_compiler_dir only if it actually exists on the file system.  Then the build system
        # can determine if it is set and should build.
        if os.path.isfile(data.local['ifort_dir'] + '/bin/compilervars.bat'):
            data.local['ifort_compiler_dir'] = data.local['ifort_dir']
    if data.local['is_linux'] == True:
        data.local['ifort_dir'] = data.local['intel_compiler_root']
        data.local['intelmkl_dir'] = os.path.join(data.local['ifort_dir'], 'mkl')
        if os.path.isfile(data.local['ifort_dir'] + '/bin/compilervars.sh'):
            data.local['ifort_compiler_dir'] = data.local['ifort_dir']
    return data

def generate_set_env(parser, args, subargs, data):
    if data.local['is_linux'] == False:
        generate_set_env_bat(parser, args, subargs, data)
    else:
        generate_set_env_bash(parser, args, subargs, data)

def generate_set_env_bat(parser, args, subargs, data):
    workspace_input_root = os.getenv('WORKSPACE_INPUT_ROOT', 'UNDEFINED').replace("\\", "/")
    workspace_output_root = os.getenv('WORKSPACE_OUTPUT_ROOT', 'UNDEFINED').replace("\\", "/")
    variant = os.getenv('SANDBOX_VARIANT', 'UNDEFINED')
    data.local['set_env_bat_previous'] = os.path.join(workspace_output_root, data.local['variants_dir_name'], variant, 'mod', 'set_env.bat').replace("\\", "/")
    data.local['set_env_bat'] = os.path.join(data.local['mod_dir'], 'set_env.bat').replace("\\", "/")
    data.local['set_env_bat_tmp'] = os.path.join(data.local['mod_dir'], 'set_env_tmp.bat').replace("\\", "/")

    __remove_file(data.local['set_env_bat_tmp'])
    compute_env_bat(data)
    write_call_set_env_bat(data)
    write_set_env_bat(data)

    files_match = False
    if os.path.isfile(data.local['set_env_bat']):
        if data.local['set_env_bat'] == data.local['set_env_bat_previous']:
            import filecmp
            files_match = filecmp.cmp(data.local['set_env_bat_tmp'], data.local['set_env_bat'])
    if not files_match:
        from shutil import copyfile
        copyfile(data.local['set_env_bat_tmp'], data.local['set_env_bat'])

    if workspace_input_root == data.local['input_tree']:
        if variant == data.options['build_variant']:
            if files_match:
                if data.options['force_set_env'] == False:
                    __remove_file(data.local['set_env_bat_tmp'])

def generate_set_env_bash(parser, args, subargs, data):
    compute_env_bash(data)
    write_call_set_env_bash(data)
    write_set_env_bash(data)

def compute_env_bat(data):
    path_data = {}

    path_data['PYTHONHOME'] = ''
    path_data['PYTHONPATH'] = ''
    path_data['PATH1'] = ''
    path_data['PATH2'] = ''
    path_data['SCA_LD_LIBRARY_PATH'] = ''

    path_data['PATH1'] += '.;'
    path_data['PATH1'] += '%WORKSPACE_INPUT_ROOT%;'
    path_data['PATH1'] += '%SystemRoot%\\system32;'
    path_data['PATH1'] += '%SystemRoot%;'
    path_data['PATH1'] += '%SystemRoot%\\system32\\WindowsPowerShell\\v1.0;'
    path_data['PATH1'] += '%SystemRoot%\\system32\\wbem;'
    path_data[
        'PATH1'] += '%WORKSPACE_OUTPUT_ROOT%\\components\\cmake\\WIN8664\\bin;'
    path_data[
        'PATH1'] += '%WORKSPACE_OUTPUT_ROOT%\\components\\ninja\\WIN8664\\bin;'
    path_data['PATH1'] += '%PYTHON_ROOT%;'
    if data.machine.get('visual_studio_unavailable', False) != True:
        path_data['PATH1'] += data.local['vs_dir'] + '\\Common7\\IDE;'

    data, path_data = compute_app_specific_path(
        data, path_data
    )  #TODO: Give PATH1, PATH2 explicitly....and maybe with more meaningful names?

    data.env2['PYTHONHOME'] = path_data['PYTHONHOME']
    data.env2['PYTHONPATH'] = path_data['PYTHONPATH']
    data.env2['SCA_LD_LIBRARY_PATH'] = path_data['SCA_LD_LIBRARY_PATH']

    path_data['PATH2'] += '%ProgramFiles%\\7-Zip;'
    path_data['PATH2'] += '%ProgramFiles(x86)%\\7-Zip;'
    path_data['PATH2'] += os.path.normpath(
        data.machine.get('additional_path', '')) + ';'
    path_data['PATH2'] += '%WORKSPACE_OUTPUT_ROOT%\\components\\doxygen;'
    path_data['PATH2'] += '%WORKSPACE_OUTPUT_ROOT%\\components\\graphviz\\bin;'

    data.local['PATH1'] = path_data['PATH1']
    data.local['PATH2'] = path_data['PATH2']

def write_call_set_env_bat(data):
    # Write out a variant independent invocation point
    if not os.path.isdir(data.local['sandbox_output_dir']):
        os.makedirs(data.local['sandbox_output_dir'])

    script_filename = data.local['sandbox_output_dir'] + '/call_set_env.bat'
    script_file = ''
    script_file = open(script_filename,
                       "w")
    script_file.write('@echo off\n')
    script_file.write('if exist ' + data.local['mod_dir'] + '\\set_env_tmp.bat (\n')
    script_file.write('    call ' + data.local['mod_dir'] + '\\set_env_tmp.bat || goto ErrorExit\n')
    script_file.write('    rm -f ' + data.local['mod_dir'] + '\\set_env_tmp.bat || goto ErrorExit\n')
    script_file.write(')\n')
    script_file.write('\n')
    script_file.write('exit /b 0\n')
    script_file.write('\n')
    script_file.write(':ErrorExit\n')
    script_file.write('exit /b 1\n')
    script_file.close()
    __wait_till_exists(script_filename)

def write_set_env_bat(data):
    # Now write out the shell script
    if not os.path.isdir(data.local['mod_dir']):
        os.makedirs(data.local['mod_dir'])

    script_filename = os.path.join(data.local['mod_dir'], 'set_env_tmp.bat')
    script_file = open(script_filename, "w")

    script_file.write('@echo off\n')
    script_file.write('goto :main\n')
    script_file.write('\n')
    script_file.write(':normalize_path\n')
    script_file.write('  set RETVAL=%~dpfn1\n')
    script_file.write('  EXIT /B\n')
    script_file.write('\n')
    script_file.write(':main\n')
    script_file.write('set VS100COMNTOOLS=\n')
    script_file.write('set VS110COMNTOOLS=\n')
    script_file.write('set VS120COMNTOOLS=\n')
    script_file.write('set VS140COMNTOOLS=\n')
    script_file.write('\n')

    script_file.write('if "%1" == "visual_studio_unavailable" (\n')
    script_file.write('    set "DO_SKIP_DEV=DEFINED"\n')
    script_file.write(')\n')
    script_file.write('\n')

    script_file.write('set "VARIANT_DIR=%~dp0"\n')
    script_file.write('set "VARIANT_DIR=%VARIANT_DIR:~0,-1%"\n')
    script_file.write('call :normalize_path "%VARIANT_DIR%\\.."\n')
    script_file.write('set "VARIANT_DIR=%RETVAL%"\n')
    script_file.write('call :normalize_path "%VARIANT_DIR%\\..\\..\\"\n')
    script_file.write('set "WORKSPACE_INPUT_ROOT=%RETVAL:~0,-8%"\n'
                      )  #TODO: Application specific
    script_file.write('call :normalize_path "%VARIANT_DIR%\\..\\.."\n')
    script_file.write('set "WORKSPACE_OUTPUT_ROOT=%RETVAL%"\n')
    script_file.write('\n')
    # Prefer the python from the source tree
    script_file.write(
        'set "PYTHON_ROOT=%WORKSPACE_INPUT_ROOT%\\tools\\python3\\WIN8664"\n'
    )  #TODO: Application specific
    # If not available, then use a copy of python, which has been published into the mod.
    # This is required when using a mod without access to the source tree.
    script_file.write('if not exist "%PYTHON_ROOT%\\" (\n')
    script_file.write('    set "PYTHON_ROOT=%VARIANT_DIR%\\mod\\leaf\\Components\\Python3"\n')
    script_file.write(')\n')
    script_file.write('\n')

    script_file.write('if not defined MSC_LICENSE_FILE (\n')
    script_file.write('    set "MSC_LICENSE_FILE=' +
                      data.network['msc_license_file'] + '"\n')
    script_file.write(')\n')
    script_file.write('\n')

    for name in sorted(data.env):
        script_file.write('set "%s=%s"\n' % (name, str(data.env[name])))
    for name in sorted(data.env2):
        script_file.write('set "%s=%s"\n' % (name, str(data.env2[name])))

    script_file.write('\n')
    script_file.write(
        '::Set the initial PATH to various system and utility locations.\n')
    script_file.write('set "PATH=' + data.local['PATH1'] + '"\n')
    if data.machine.get('visual_studio_unavailable', False) != True:
        script_file.write('\n')
        script_file.write('if not defined DO_SKIP_DEV (\n')
        script_file.write('\n')
        script_file.write('set "INCLUDE="\n')
        script_file.write('set "LIB="\n')
        script_file.write('set "LIBPATH="\n')
        script_file.write('set "CLASSPATH="\n')
        script_file.write('set "MIC_LD_LIBRARY_PATH="\n')
        script_file.write('set "MIC_LIBRARY_PATH="\n')
        script_file.write('set "CPATH="\n')
        script_file.write('set "LD_LIBRARY_PATH="\n')
        script_file.write(
            '::Initialize Visual Studio environment, including adding to PATH.\n'
        )
        script_file.write(
            'pushd .\n'
        )  # This is necessary since vcvarsall.bat might change the current directory.
        script_file.write(
            'call "' + data.local['vs_dir'] +
            '/Common7/Tools/VsDevCmd.bat" -arch=amd64 -winsdk=10.0.18362.0 -vcvars_ver=14.16.27023 -no_logo || goto ErrorVsEnv\n'
        )
        script_file.write('popd\n')
        ifort_compiler = data.local['ifort_dir'] + '/bin/compilervars.bat'
        if os.path.isfile(ifort_compiler):
            script_file.write(
                '::Initialize Intel Fortran environment, including adding to PATH (many duplicates here).\n'
            )
            script_file.write(
                'pushd .\n'
            )  # This is necessary since vcvarsall.bat might change the current directory.
            script_file.write(
                'call "' + ifort_compiler + '" intel64 vs2017 quiet || goto ErrorIntelEnv\n'
            )
            script_file.write('popd\n')
        script_file.write('set "__DOTNET_ADD_64BIT="\n')
        script_file.write('set "__DOTNET_PREFERRED_BITNESS="\n')
        script_file.write('set "__VSCMD_PREINIT_INCLUDE="\n')
        script_file.write('set "__VSCMD_PREINIT_PATH="\n')
        script_file.write('set "__VSCMD_PREINIT_VCToolsVersion="\n')
        script_file.write('set "__VSCMD_PREINIT_VS150COMNTOOLS="\n')
        script_file.write(')\n')
        script_file.write('set "DO_SKIP_DEV="\n')
        script_file.write('\n')
        script_file.write(
            '::Remove duplicate entries in PATH. This routine can handle PATHs up to ~6300 characters.\n'
        )
        script_file.write('setlocal EnableDelayedExpansion\n')
        script_file.write('set SHORTPATH=\n')
        script_file.write('for %%p in ("%PATH:;=";"%") do (\n')
        script_file.write('call :addtopath %%p\n')
        script_file.write(')\n')
        script_file.write('goto :egress\n')
        script_file.write(':addtopath\n')
        script_file.write('set "PATHITEM=%*"\n')
        script_file.write('set PATHITEM=%PATHITEM:"=%;\n')
        script_file.write('if not defined SHORTPATH (\n')
        script_file.write('set "SHORTPATH=%PATHITEM%"\n')
        script_file.write('goto :EOF\n')
        script_file.write(')\n')
        script_file.write('if "%SHORTPATH%" == "!SHORTPATH:%PATHITEM%=!" (\n')
        script_file.write('set "SHORTPATH=%SHORTPATH%%PATHITEM%"\n')
        script_file.write(')\n')
        script_file.write('goto :EOF\n')
        script_file.write(':egress\n')
        script_file.write('endlocal & set PATH=%SHORTPATH%\n')
        script_file.write('\n')

    script_file.write('::Now add any additional paths.\n')
    script_file.write('set "PATH=%PATH%;' + data.local['PATH2'] + '"\n')
    script_file.write('\n')
    script_file.write('exit /b 0\n')
    script_file.write(':ErrorVsEnv\n')
    script_file.write(
        "echo ERROR: Occurred when running the Visual Studio environment initialization script 'VsDevCmd.bat'\n"
    )
    script_file.write('exit /b 1\n')
    script_file.write(':ErrorIntelEnv\n')
    script_file.write(
        "echo ERROR: Occurred when running the Intel Fortran environment initialization script 'compilervars.bat'\n"
    )
    script_file.write('exit /b 1\n')
    script_file.close()
    __wait_till_exists(script_filename)

    with open(data.local['previous_options_file'], 'w') as out_file:
        json.dump(
            data.options,
            out_file,
            ensure_ascii=False,
            indent=2,
            sort_keys=True)

def compute_env_bash(data):
    # Copy common env to linux
    data.env_linux['SANDBOX_VARIANT'] = data.env['SANDBOX_VARIANT']
    data.env_linux['SKIPTESTEXECUTION'] = data.local['SKIPTESTEXECUTION']

    data.env_linux['LEAF_DIR'] = data.env['LEAF_DIR'].replace("\\", "/")
    data.env_linux['SCASYSTEM_RUNTIME'] = data.env[
        'SCASYSTEM_RUNTIME'].replace("\\", "/")
    data.env_linux['AEM_RUNTIME'] = data.env['AEM_RUNTIME'].replace("\\", "/")
    data.env_linux['EOM_RUNTIME'] = data.env['EOM_RUNTIME'].replace("\\", "/")
    data.env_linux['SPF_RUNTIME'] = data.env['SPF_RUNTIME'].replace("\\", "/")
    data.env_linux['APEX_PUBLISH_RUNTIME'] = data.env[
        'APEX_PUBLISH_RUNTIME'].replace("\\", "/")
    data.env_linux[
        'PYTHON_ROOT'] = '$WORKSPACE_INPUT_ROOT/tools/python3/LX8664_RHE73'

    # These variables depend on the first env_linux
    path = ''
    path += '$WORKSPACE_OUTPUT_ROOT/components/cmake/LX8664/bin:'
    path += '$WORKSPACE_OUTPUT_ROOT/components/ninja/LX8664/bin:'
    path += '$WORKSPACE_OUTPUT_ROOT/components/doxygen:'
    path += '$PYTHON_ROOT/bin:'
    path += '/usr/local/bin:'
    path += '/usr/bin:'
    path += os.path.normpath(data.machine.get('additional_path', '')) + ':'

    python_path = ''
    python_path += '$WORKSPACE_INPUT_ROOT/tools/scascons:'
    python_path += '$WORKSPACE_INPUT_ROOT/tools/testrunner/bin:'
    python_path += '$SCASYSTEM_RUNTIME/lib/python:'

    ld_library_path = ''
    sca_resource_dir = ''

    ld_library_path += '$LEAF_DIR/Components/shared/lib:'

    ld_library_path += '$SCASYSTEM_RUNTIME/' + data.local['os_platform'] + '/lib:'
    sca_resource_dir += '$SCASYSTEM_RUNTIME/res:'

    ld_library_path += '$EOM_RUNTIME/' + data.local['os_platform'] + '/lib:'
    ld_library_path += '$EOM_RUNTIME/' + data.local['os_platform'] + '/lib/SCA/EOM:'
    ld_library_path += '$EOM_RUNTIME/' + data.local['os_platform'] + '/lib/SCA/PersistanceFW:'
    sca_resource_dir += '$EOM_RUNTIME/res:'

    ld_library_path += '$SPF_RUNTIME/' + data.local['os_platform'] + '/lib:'
    sca_resource_dir += '$SPF_RUNTIME/res:'

    ld_library_path += '$AEM_RUNTIME/' + data.local['os_platform'] + '/lib:'
    sca_resource_dir += '$AEM_RUNTIME/res:'

    ld_library_path += '$PYTHON_ROOT/lib:'

    data.env_linux2['SCA_RESOURCE_DIR'] = sca_resource_dir
    data.env_linux2['SCA_CATALOG_DIR'] = sca_resource_dir
    data.env_linux2['LD_LIBRARY_PATH'] = ld_library_path
    data.env_linux2['PATH'] = path
    data.env_linux2['PYTHONPATH'] = python_path

def write_call_set_env_bash(data):
    # Write out a variant independent invocation point
    if not os.path.isdir(data.local['sandbox_output_dir']):
        os.makedirs(data.local['sandbox_output_dir'])

    script_file = ''
    script_file = open(data.local['sandbox_output_dir'] + '/call_set_env.sh',
                       "w")
    script_file.write('#!/usr/bin/bash\n')
    script_file.write('source ' + data.local['mod_dir'] + '/set_env.sh\n')
    script_file.close()

def write_set_env_bash(data):
    # Now write out the shell script
    if not os.path.isdir(data.local['mod_dir']):
        os.makedirs(data.local['mod_dir'])

    script_file = open(data.local['mod_dir'] + '/set_env.sh', "w")

    script_file.write('#!/usr/bin/bash\n')
    # Find the path of this script
    script_file.write(
        'export APPLICATION_TOP="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"\n'
    )

    # Find absolute path from relative path
    script_file.write(
        'export WORKSPACE_OUTPUT_ROOT="$(realpath $APPLICATION_TOP/../../..)"\n'
    )
    # Remove _output
    script_file.write(
        'export WORKSPACE_INPUT_ROOT="${WORKSPACE_OUTPUT_ROOT::-7}"\n')
    script_file.write('export VARIANT_DIR="$(realpath $APPLICATION_TOP/..)"\n')
    script_file.write('\n')

    script_file.write('if [[ "${MSC_LICENSE_FILE:-0}" = "0" ]]; then\n')
    script_file.write('  export MSC_LICENSE_FILE="' +
                      data.network['msc_license_file'] + '"\n')
    script_file.write('fi\n')
    script_file.write('\n')

    for name in sorted(data.env_linux):
        script_file.write(
            'export %s="%s"\n' % (name, str(data.env_linux[name])))
    for name in sorted(data.env_linux2):
        script_file.write(
            'export %s="%s"\n' % (name, str(data.env_linux2[name])))

    # Only set the compiler environment if compilers are available on the machine
    if data.machine.get('visual_studio_unavailable', False) != True:
        script_file.write('\n')
        # The following are appended by the Intel setup so must be cleared
        script_file.write('unset MANPATH\n')
        script_file.write('unset INTEL_LICENSE_FILE\n')
        script_file.write('unset LIBRARY_PATH\n')
        script_file.write('unset MIC_LD_LIBRARY_PATH\n')
        script_file.write('unset MIC_LIBRARY_PATH\n')
        script_file.write('unset CPATH\n')
        script_file.write('unset NLSPATH\n')
        script_file.write('unset CLASSPATH\n')
        script_file.write('unset INFOPATH\n')
        script_file.write('source ' + data.local['ifort_dir'] +'/bin/compilervars.sh intel64\n')
    script_file.close()

    with open(data.local['previous_options_file'], 'w') as out_file:
        json.dump(data.options, out_file, indent=2, sort_keys=True)

def __remove_file(filename):
    import time
    if os.path.isfile(filename):
        os.remove(filename)
    # Retry loop because:
    # 1) Windows may hold onto a file for a while if anti-virus is busy with it
    # 2) Windows has a known race condition:
    # https://blogs.msdn.microsoft.com/oldnewthing/20120907-00/?p=6663/
    retries = 0
    max_retries = 50
    while (os.path.isfile(filename)) and retries < max_retries:
        time.sleep(0.100)
        retries += 1

def __wait_till_exists(filename):
    import time
    if os.path.isfile(filename):
        return
    # Retry loop because:
    # 1) Windows may hold onto a file for a while if anti-virus is busy with it
    # 2) Windows has a known race condition:
    # https://blogs.msdn.microsoft.com/oldnewthing/20120907-00/?p=6663/
    retries = 0
    max_retries = 50
    while (not os.path.isfile(filename)) and retries < max_retries:
        time.sleep(0.100)
        retries += 1

if __name__ == "__main__":
    STATUS = main(sys.argv[1:])
    sys.exit(STATUS)
