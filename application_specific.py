import os
import sys
import logging
import collections
import socket
import time
import glob
import subprocess
from datetime import datetime
import xml.dom.minidom
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import SubElement
from helpers import _call_command
from helpers import blast_build
from helpers import copy_src_dst_tuples
from helpers import _print_verbosity1
from helpers import _print_verbosity2
from helpers import append_RelativeProject_roots
from helpers import _get_variant_dir_env_variable
from helpers import _get_workspace_output_root_env_variable
from helpers import _get_scons_variant_dir as _get_variant_dir
from helpers import enableComponentCache
from helpers import clean_component
from helpers import publish_component
from helpers import disableComponentCache
from helpers import isComponentEnabled
from helpers import _install_federated_database
from helpers import _cache_comp
from helpers import checkSolutionsValidImpl
from helpers import _clean_tests
from helpers import isComponentCacheEnabled
from helpers import _warn_on_long_workspace_path
from helpers import blast_idl_build
import json

sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', '..'))
import apex_info

sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', '..', 'componentcache', 'noarch'))
from componentcache import the_component_cache
import utilities
from blast import clean_ide
from blast import clean_variant
from blast import generate_ide
import storage

import shutil
def _copyfileobj_patched(fsrc, fdst, length=16*1024*1024):
    """Patches shutil method to hugely improve copy speed"""
    while 1:
        buf = fsrc.read(length)
        if not buf:
            break
        fdst.write(buf)
shutil.copyfileobj = _copyfileobj_patched

def get_workspace_machine_file_path(data):
    return os.path.join(data.local['output_tree'], 'sandbox', 'apex_sandbox_machine_file.json')

def get_shared_machine_file_path(data):
    return data.local['sandbox_input_dir'] + '/machines/' + socket.gethostname() + '.json'

def app_specific_folders(data):
    data.local['variants_dir_name'] = 'variants'

    data.local['release_name']     = 'release'
    data.local['debug_name']       = 'debug'
    data.local['vtune_name']       = 'vtune'
    return data

def get_app_specific_bom_file(data):
    return os.path.join(data.local['input_tree'], 'tools', 'bom_apex.json')

def get_compilation_roots(data):
    # Structure: 'alias': ('delivery alias', 'action', 'source dir',                  'alias_RUNTIME dir', 'Bin DIR' (same as alias_RUNTIME if None), should_generate_solution?, 'solution filename', 'scons unique build options', 'language')
    dr = collections.OrderedDict()

    dr['testsupport_cs'] =       ('leaf', scons_build, 'Framework/TestSupport',         'Framework/TestSupport_CS', None, True, 'TestSupport.sln', '', 'C#')
    dr['testsupport'] =       ('leaf', blast_build, 'Framework/TestSupport',          'Framework/TestSupport', None, True, 'TestSupport.sln', '', 'C++')
    dr['eom'] =               ('leaf', conditional_build, 'Services/EOM',                   'Services/EOM',       None, True,  'EOM.sln', 'FCOMPILER=intel SCACATALOG="SCAServiceCatalog.xml" UNITYBUILD', 'C++')

    dr['clef_v1types'] =     ( 'leaf', scons_build, 'Deliveries/clef/idltypes',       'Framework/IDLTypes', None, False, '', 'IDLTypesDotNet MSVSPROJECTS=no SEPARATEOBJUNIQUEID=CLEF', 'IDL')
    # a new sandbox flag named IDLTYPESAPPEND has been added to trigger the named IDLTypesDontNet dll builds.
    # any build with the IDLTYPESAPPEND flag will build a dll named for the dag
    # the DLL will be put next to the rest of dag SCA output in <xxx_RUNTIME)/WIN8664/lib
    # for example, this core_plugin dag will build IDLTypesDotNetcore_plugin.dll
    dr['tetmesh'] =           ('leaf', scons_build, 'Services/tetmesh/source',        'Services/tetmesh', None, False, 'tetmesh.sln', '', 'C++')
    dr['tetmesh_test'] =      ('leaf', scons_build, 'Services/tetmesh/source',        '../../tests', None, False, 'tetmesh_test.sln', '', 'C++')
    dr['appframe'] =          ('leaf', blast_build, 'Framework/AppFrame',             'Framework/AppFrame', None, True, 'AppFrame.sln', 'IDLTYPESAPPEND', 'C++')
    dr['vtk_wrapper'] =       ('leaf', blast_build, 'Services/VTKWrapper',            'Services/VTKWrapper', None, True, 'VTKWrapper.sln', '', 'C++')
    dr['gen'] =               ('leaf', blast_build, 'Services/gen',                   'Services/GEN/apps',  None, False,'source.sln', '', 'C++')
    dr['clef_sdk'] =          ('leaf', blast_build, 'Deliveries/clef/apex_sdk',       'Deliveries/clef/apex_sdk', None, False, '', '', 'Publish')
    dr['ddm'] =               ('leaf', blast_build, 'Services/Display3DDataManager',  'Services/Display3DDataManager/apps', None, False, 'ddm.sln', 'IDLTYPESAPPEND', 'C++')
    dr['core_plugin'] =       ('leaf', blast_build, 'Plugins/CorePlugin',             'Plugins/CorePlugin/SCA_Services', 'Framework/AppFrame', True,  'CorePlugin.sln', 'IDLTYPESAPPEND', 'C++')
    dr['shell_plugin'] =      ('leaf', blast_build, 'Plugins/ShellPlugin',            'Plugins/ShellPlugin/SCA_Services', 'Framework/AppFrame', True,  'ShellPlugin.sln', 'IDLTYPESAPPEND', 'C++')
    dr['display_plugin'] =    ('leaf', blast_build, 'Plugins/DisplayPlugin',          'Plugins/DisplayPlugin/SCA_Services', 'Framework/AppFrame', True,  'DisplayPlugin.sln', 'IDLTYPESAPPEND', 'C++')
    dr['clef_remoting'] =     ('leaf', blast_build, 'Deliveries/clef/remoting',       'Deliveries/clef/remoting',  None, False, 'remoting.sln', '', 'C++')
    dr['clef_scripting'] =    ('leaf', blast_build, 'Deliveries/clef/scripting',      'Deliveries/clef/scripting', None, False, 'scripting.sln', '', 'C++')
    dr['uiservices'] =        ('leaf', scons_build, 'Framework/UIServices',           'Framework/UIServices',  None, False, 'UIServices.sln', 'IDLTYPESAPPEND', 'C#')
    dr['uiframework'] =       ('leaf', blast_build, 'Framework/UIFramework',          'Framework/UIFramework', 'Framework/AppFrame', False, 'Predator.sln', '', 'C#')
    dr['core_plugin_ui'] =    ('leaf', blast_build, 'Plugins/CorePlugin/UI',          'Plugins/CorePlugin/SCA_Services', 'Framework/AppFrame', False, 'CorePluginUI.sln', '', 'C#')
    dr['shell_plugin_ui'] =   ('leaf', blast_build, 'Plugins/ShellPlugin/UI',         'Plugins/ShellPlugin/SCA_Services', 'Framework/AppFrame', False, 'ShellPluginUI.sln', '', 'C#')
    dr['display_plugin_ui'] = ('leaf', blast_build, 'Plugins/DisplayPlugin/UI',       'Plugins/DisplayPlugin/SCA_Services', 'Framework/AppFrame', False, 'DisplayPluginUI.sln', '', 'C#')
    dr['leaf_publish'] =      ('leaf', blast_build, 'Deliveries/leaf/publish',                              '', 'Framework/AppFrame', False, '', '', 'Publish')
    dr['dgk'] =               ('leaf', blast_build, 'Services/DGK/source',            'Services/DGK/DGK/Apps', None, False, 'source.sln', 'IDLTYPESAPPEND UNITYBUILD', 'C++')
    dr['gsc'] =               ('leaf', blast_build, 'Services/GSC/source',            'Services/GSC/GSC/Apps', None, False, 'source.sln', 'IDLTYPESAPPEND', 'C++')
    dr['mgc'] =               ('leaf', blast_build, 'Services/MGC/source',            'Services/MGC/MGC/Apps', None, False, 'source.sln', 'IDLTYPESAPPEND', 'C++')
    dr['muc'] =               ('leaf', blast_build, 'Services/MUC',                   'Services/MUC/apps',     None, False, 'MUC.sln', 'IDLTYPESAPPEND', 'C++')
    dr['base_plugin'] =       ('leaf', blast_build, 'Plugins/BasePlugin',             'Plugins/BasePlugin/SCA_Services', 'Framework/AppFrame', True,  'BasePlugin.sln', 'IDLTYPESAPPEND', 'C++')
    dr['geom_plugin'] =       ('leaf', blast_build, 'Plugins/GeomPlugin',             'Plugins/GeomPlugin/SCA_Services', 'Framework/AppFrame', True,  'GeomPlugin.sln', 'IDLTYPESAPPEND UNITYBUILD', 'C++')
    dr['measure_plugin'] =    ('leaf', blast_build, 'Plugins/MeasurePlugin',          'Plugins/MeasurePlugin/SCA_Services', 'Framework/AppFrame', True,  'MeasurePlugin.sln', 'IDLTYPESAPPEND', 'C++')
    dr['transform_plugin'] =  ('leaf', blast_build, 'Plugins/TransformPlugin',        'Plugins/TransformPlugin/SCA_Services', 'Framework/AppFrame', True,  'TransformPlugin.sln', 'IDLTYPESAPPEND', 'C++')
    dr['midsurf_plugin'] =    ('leaf', blast_build, 'Plugins/MidSurfPlugin',          'Plugins/MidSurfPlugin/SCA_Services', 'Framework/AppFrame', True,  'MidSurfPlugin.sln', 'IDLTYPESAPPEND', 'C++')
    dr['geomdebug_plugin'] =  ('leaf', blast_build, 'Plugins/GeomDebugPlugin',        'Plugins/GeomDebugPlugin/SCA_Services', 'Framework/AppFrame', True,  'GeomDebugPlugin.sln', 'IDLTYPESAPPEND UNITYBUILD', 'C++')
    dr['glef_scripting'] =    ('leaf', blast_build, 'Deliveries/glef/scripting',      'Deliveries/glef/scripting', None, False, 'scripting.sln', '', 'C++')
    dr['base_plugin_ui'] =    ('leaf', blast_build, 'Plugins/BasePlugin/UI',          'Plugins/BasePlugin/SCA_Services', 'Framework/AppFrame', False, 'BasePluginUI.sln', '', 'C#')
    dr['geometry_plugin_ui'] =('leaf', blast_build, 'Plugins/GeomPlugin/UI',          'Plugins/GeomPlugin/SCA_Services', None, False, 'GeomPluginUI.sln', '', 'C#')
    dr['geometry_plugin_gui'] =('leaf', blast_build, 'Plugins/GeomPlugin/GUI',          'Plugins/GeomPlugin/SCA_Services', None, False, 'GeomPluginGUI.sln', '', 'C#')
    dr['measure_plugin_ui'] = ('leaf', blast_build, 'Plugins/MeasurePlugin/UI',       'Plugins/MeasurePlugin/SCA_Services', None, False, 'MeasurePluginUI.sln', '', 'C#')
    dr['transform_plugin_ui']=('leaf', blast_build, 'Plugins/TransformPlugin/UI',     'Plugins/TransformPlugin/SCA_Services', None, False, 'TransformPluginUI.sln', '', 'C#')
    dr['transform_plugin_gui']=('leaf', blast_build, 'Plugins/TransformPlugin/GUI',     'Plugins/TransformPlugin/SCA_Services', None, False, 'TransformPluginGUI.sln', '', 'C#')
    dr['midsurface_plugin_ui']=('leaf', blast_build, 'Plugins/MidSurfPlugin/UI',      'Plugins/MidSurfPlugin/SCA_Services', None, False, 'MidSurfPluginUI.sln', '', 'C#')
    dr['geomdebug_plugin_ui']=('leaf', blast_build, 'Plugins/GeomDebugPlugin/UI',     'Plugins/GeomDebugPlugin/SCA_Services', None, False, 'GeomDebugPluginUI.sln', '', 'C#')
    dr['geomdebug_plugin_gui']=('leaf', blast_build, 'Plugins/GeomDebugPlugin/GUI',     'Plugins/GeomDebugPlugin/SCA_Services', None, False, 'GeomDebugPluginGUI.sln', '', 'C#')

    dr['aem_idl'] =           ('leaf', conditional_idl_build, 'Services/AEM',                    'Services/AEM', None, True, 'AEM.sln', 'IDLTYPESAPPEND FCOMPILER=intel SCACATALOG="SCAServiceCatalog.xml" UNITYBUILD idl', 'C++')
    dr['spf'] =               ('leaf', conditional_build, 'Services/SPF',              'Services/SPF', None, True, '', 'MSVSPROJECTS=no FCOMPILER=intel SKIPTESTEXECUTION=True', 'C++')
    dr['cosim_cpp'] =         ('leaf', blast_build, 'Services/CoSim/cpp', 'Services/CoSim/cpp', None, True, '', 'FCOMPILER=intel SKIPTESTEXECUTION=True', 'C++')
    dr['aem'] =               ('leaf', conditional_build, 'Services/AEM',                    'Services/AEM',       None, True,  'AEM.sln', 'IDLTYPESAPPEND FCOMPILER=intel SCACATALOG="SCAServiceCatalog.xml" UNITYBUILD', 'C++')
    dr['mqc'] =               ('leaf', blast_build, 'Services/MQC',                    'Services/MQC/apps',     None, False, 'MQC.sln', 'IDLTYPESAPPEND', 'C++')
    dr['mtb'] =               ('leaf', blast_build, 'Services/MGC/TestDriver/MTB/source', '../../tests/MTB/MTB/Apps', None, False, 'source.sln', 'IDLTYPESAPPEND', 'C++')
    dr['ftc'] =               ('leaf', blast_build, 'Services/FTC/source',             'Services/FTC/apps', None, False, 'source.sln', 'IDLTYPESAPPEND UNITYBUILD', 'C++')
    dr['fem_plugin'] =        ('leaf', blast_build, 'Plugins/FEMPlugin',               'Plugins/FEMPlugin/SCA_Services', None, True,  'FEMPlugin.sln', 'IDLTYPESAPPEND UNITYBUILD', 'C++')
    dr['fem_plugin_ui'] =     ('leaf', blast_build, 'Plugins/FEMPlugin/UI',            'Plugins/FEMPlugin/SCA_Services', None, False, 'FEMPluginUI.sln', '', 'C#')
    dr['fem_plugin_gui'] =     ('leaf', blast_build, 'Plugins/FEMPlugin/GUI',            'Plugins/FEMPlugin/SCA_Services', None, False, 'FEMPluginGUI.sln', '', 'C#')

    dr['chart_plugin'] =      ('leaf', blast_build, 'Plugins/ChartPlugin',            'Plugins/ChartPlugin/SCA_Services', None, True, 'ChartPlugin.sln', 'IDLTYPESAPPEND', 'C++')
    dr['chart_plugin_ui']=    ('leaf', blast_build, 'Plugins/ChartPlugin/UI',         'Plugins/ChartPlugin/SCA_Services', None, False, 'ChartPluginUI.sln', '', 'C#')

    dr['hello_plugin'] =      ('helloapp', blast_build, 'Plugins/HelloPlugin',        'Plugins/HelloPlugin/SCA_Services', None, True, 'HelloPlugin.sln', 'IDLTYPESAPPEND', 'C++')
    dr['hello_plugin_ui'] =   ('helloapp', blast_build, 'Plugins/HelloPlugin/UI',     'Plugins/HelloPlugin/SCA_Services', None, False, 'HelloPluginUI.sln', '', 'C#')
    dr['hello_plugin_gui'] =  ('helloapp', blast_build, 'Plugins/HelloPlugin/GUI',    'Plugins/HelloPlugin/SCA_Services', None, False, 'HelloPluginGUI.sln', '', 'C#')

    ### Example directives for a new plugin.
    # dr['testabc_plugin'] =  ('leaf', blast_build, 'Plugins/TestABCPlugin',  'Plugins/TestABCPlugin/SCA_Services', None, True, 'TestABCPlugin.sln', 'IDLTYPESAPPEND', 'C++')
    # dr['testabc_plugin_ui']= ('leaf', blast_build, 'Plugins/TestABCPlugin/UI', 'Plugins/TestABCPlugin/SCA_Services', None, False, 'TestABCPluginUI.sln', '', 'C#')
    # dr['testabc_plugin_gui']= ('leaf', blast_build, 'Plugins/TestABCPlugin/GUI', 'Plugins/TestABCPlugin/SCA_Services', None, False, 'TestABCPluginGUI.sln', '', 'C#')


    dr['ctc'] =               ('apex', blast_build, 'Services/CTC',                      'Services/CTC/apps', None, False, 'CTC.sln', 'IDLTYPESAPPEND UNITYBUILD', 'C++')
    dr['thd'] =               ('apex', blast_build, 'Services/THD/THDCore',              'Services/THD/THD/Apps', None, False, 'THDCore.sln', 'IDLTYPESAPPEND', 'C++')
    dr['thd_test'] =          ('apex', blast_build, 'Services/THD/TestDriver', '../../tests/THD/THDClient/Apps', None, False, 'THDClient.sln', '', 'C++')
    dr['post'] =              ('leaf', blast_build, 'Services/Post/source',              'Services/Post/apps', None, False, 'source.sln', 'IDLTYPESAPPEND', 'C++')
    dr['motion'] =            ('apex', blast_build, 'Services/motion/source/',           'Services/Motion/Apps', None, True,  'source.sln', 'IDLTYPESAPPEND', 'C++')
    dr['acs'] =               ('apex', blast_build, 'Services/acs',                      'Services/acs', None, False, 'acs.sln', 'IDLTYPESAPPEND', 'C++')
    dr['thd_plugin'] =        ('apex', blast_build, 'Plugins/THDPlugin',                 'Plugins/THDPlugin/SCA_Services', None, True,  'THDPlugin.sln', 'BUILDCPP=1 IDLTYPESAPPEND', 'C++')
    dr['study_plugin'] =      ('apex', blast_build, 'Plugins/StudyPlugin',               'Plugins/StudyPlugin/SCA_Services', None, True,  'StudyPlugin.sln', 'BUILDCPP=1 IDLTYPESAPPEND', 'C++')
    dr['modeling_plugin'] =   ('apex', blast_build, 'Plugins/ModelingPlugin',            'Plugins/ModelingPlugin/SCA_Services', None, True,  'ModelingPlugin.sln', 'IDLTYPESAPPEND UNITYBUILD', 'C++')
    dr['motion_plugin'] =     ('apex', blast_build, 'Plugins/MotionPlugin',              'Plugins/MotionPlugin/SCA_Services', None, True,  'MotionPlugin.sln', 'IDLTYPESAPPEND', 'C++')
    dr['poc_plugin'] =  ('helloapp', blast_build, 'Plugins/POCPlugin',  'Plugins/POCPlugin/SCA_Services', None, True, 'POCPlugin.sln', 'IDLTYPESAPPEND', 'C++')
    dr['poc_plugin_ui']= ('helloapp', blast_build, 'Plugins/POCPlugin/UI', 'Plugins/POCPlugin/SCA_Services', None, False, 'POCPluginUI.sln', '', 'C#')
    dr['poc_plugin_gui']= ('helloapp', blast_build, 'Plugins/POCPlugin/GUI', 'Plugins/POCPlugin/SCA_Services', None, False, 'POCPluginGUI.sln', '', 'C#')
    dr['marc_plugin'] =       ('apex', blast_build, 'Plugins/MarcPlugin',                'Plugins/MarcPlugin/SCA_Services', None, True, 'MarcPlugin.sln', 'IDLTYPESAPPEND', 'C++')
    dr['post_plugin'] =       ('apex', blast_build, 'Plugins/PostPlugin',                'Plugins/PostPlugin/SCA_Services', None, True,  'PostPlugin.sln', 'IDLTYPESAPPEND UNITYBUILD', 'C++')
    dr['gendes_plugin'] =     ('apex', blast_build, 'Plugins/GenDesPlugin',              'Plugins/GenDesPlugin/SCA_Services', None, True,  'GenDesPlugin.sln', 'BUILDCPP=1 IDLTYPESAPPEND', 'C++')
    dr['gendes_scripting'] =  ('gendes', blast_build, 'Deliveries/gendes/scripting',     'Deliveries/gendes/scripting', None, False, 'scripting.sln', '', 'C++')
    dr['adams_plugin'] =      ('apex', blast_build, 'Plugins/AdamsPlugin',               'Plugins/AdamsPlugin/SCA_Services',    None, True,  'AdamsPlugin.sln', 'BUILDCPP=1 IDLTYPESAPPEND', 'C++')
    dr['charting_plugin'] =   ('apex', blast_build, 'Plugins/ChartingPlugin',            'Plugins/ChartingPlugin/SCA_Services',    None, True,  'ChartingPlugin.sln', 'BUILDCPP=1 IDLTYPESAPPEND', 'C++')
    dr['demo_plugin'] =       ('apex', blast_build, 'Plugins/DemoPlugin',                'Plugins/DemoPlugin/SCA_Services',    None, True,  'DemoPlugin.sln', 'IDLTYPESAPPEND', 'C++')
    dr['apex_scripting'] =    ('apex', blast_build, 'Deliveries/apex/scripting',         'Deliveries/apex/scripting', None, False, 'scripting.sln', '', 'C++')
    dr['thd_plugin_ui'] =     ('apex', blast_build, 'Plugins/THDPlugin/UI',                 'Plugins/THDPlugin/SCA_Services', None, False, 'THDPluginUI.sln', '', 'C#')
    dr['gendes_plugin_ui'] =  ('apex', blast_build, 'Plugins/GenDesPlugin/UI',           'Plugins/GenDesPlugin/SCA_Services', None, False, 'GenDesPluginUI.sln', '', 'C#')
    dr['modeling_plugin_ui'] =('apex', blast_build, 'Plugins/ModelingPlugin/UI',         'Plugins/ModelingPlugin/SCA_Services', None, False, 'ModelingPluginUI.sln', '', 'C#')
    dr['modeling_plugin_gui']=('apex', blast_build, 'Plugins/ModelingPlugin/GUI',        'Plugins/ModelingPlugin/SCA_Services', None, False, 'ModelingPluginGUI.sln', '', 'C#')
    dr['motion_plugin_ui'] =  ('apex', blast_build, 'Plugins/MotionPlugin/UI',           'Plugins/MotionPlugin/SCA_Services', None, False, 'MotionPluginUI.sln', '', 'C#')
    dr['marc_plugin_ui'] =    ('apex', blast_build, 'Plugins/MarcPlugin/UI',             'Plugins/MarcPlugin/SCA_Services', None, False, 'MarcPluginUI.sln', '', 'C#')
    dr['post_plugin_ui'] =    ('apex', blast_build, 'Plugins/PostPlugin/UI',             'Plugins/PostPlugin/SCA_Services', None, False, 'PostPluginUI.sln', '', 'C#')
    dr['study_plugin_ui'] =   ('apex', blast_build, 'Plugins/StudyPlugin/UI',            'Plugins/StudyPlugin/SCA_Services', None, False, 'StudyPluginUI.sln', '', 'C#')
    dr['demo_plugin_ui'] =    ('apex', blast_build, 'Plugins/DemoPlugin/UI',             'Plugins/DemoPlugin/SCA_Services',    None, False, 'DemoPluginUI.sln', '', 'C#')
    dr['demo_plugin_gui'] =    ('apex', blast_build, 'Plugins/DemoPlugin/GUI',             'Plugins/DemoPlugin/SCA_Services',    None, False, 'DemoPluginGUI.sln', '', 'C#')
    dr['gendes_plugin_ui'] =  ('apex', blast_build, 'Plugins/GenDesPlugin/UI',           'Plugins/GenDesPlugin/SCA_Services', None, False, 'GenDesPluginUI.sln', '', 'C#')
    dr['adams_plugin_ui'] =   ('apex', blast_build, 'Plugins/AdamsPlugin/UI',            'Plugins/AdamsPlugin/SCA_Services', None, False, 'AdamsPluginUI.sln', '', 'C#')
    dr['adams_plugin_gui'] =  ('apex', blast_build, 'Plugins/AdamsPlugin/GUI',           'Plugins/AdamsPlugin/SCA_Services', None, False, 'AdamsPluginGUI.sln', '', 'C#')
    dr['charting_plugin_ui'] =('apex', blast_build, 'Plugins/ChartingPlugin/UI',         'Plugins/ChartingPlugin/SCA_Services', None, False, 'ChartingPluginUI.sln', '', 'C#')
    dr['adams_scripting'] =   ('apex', blast_build, 'Deliveries/adams/scripting',        'Deliveries/adams/scripting', None, False, 'scripting.sln', '', 'C++')

    dr['helloapp_documentation'] =('helloapp', blast_build, 'Deliveries/helloapp/Documentation', 'Deliveries/helloapp/Documentation', None, False, 'documentation.sln', '', 'C++')
    # the helloapp_scripting packaging step will merge the hello_plugin, clef, glef, and apex  SModules into the helloapp module
    dr['helloapp_scripting'] =('helloapp', blast_build, 'Deliveries/helloapp/scripting', 'Deliveries/helloapp/scripting', None, False, 'scripting.sln', '', 'C++')
    # publish helloapp from deliveries into mod
    dr['helloapp_publish'] =  ('helloapp', blast_build, 'Deliveries/helloapp/publish',                      '', 'Application/AppFrame', False, '', '', 'Publish')

    dr['apex_publish'] =      ('apex', blast_build, 'Deliveries/apex/publish',                                 '', '', False, '', '', 'Publish')
    dr['gendes_publish']=     ('gendes', blast_build, 'Deliveries/gendes/publish',                             '', 'Application/AppFrame', False, '', '', 'Publish')
    dr['adams_publish']=      ('adams', blast_build, 'Deliveries/adams/publish',                               '','Application/AppFrame', False, '', '', 'Publish')
    dr['genskeleton'] =       ('genskeleton', idl_build, 'Framework/GenSkeleton',        '../../genskeleton', None, False, '', '', 'GenSkeleton')

    return dr

def command_line_options(subparsers, data):
    subparser = subparsers.add_parser('scons', help='Build the current solutions with the build with the designated build system.')
    subparser.set_defaults(func=subcommand_build)
    subparser.add_argument('-s', '--solution', help= \
        'Select the solutions(s) to build. Select multiple solutions as a comma separated list with no spaces. Leave empty to build ALL solutions in the following order: \
        ' + get_build_solutions(data)
    )
    subparser.add_argument('-p', '--project', help='Specify the project to build within a solution.')
    subparser.add_argument('-l', '--language', help='Specify the one language to build.  Leave empty to build ALL languages in the following order: C++,C#,Publish')
    subparser.add_argument('-r', '--remaining', action='store_true', default=False, help='Build all remaining solutions after the specified solution.')
    subparser.add_argument('-k', '--keepgoing', action='store_true', default=False, help='Continue building other build graphs even if one fails.')
    subparser.add_argument('-c', '--cleantests', action='store_true', default=False, help='Clean and republish the tests output directory.')
    subparser.add_argument('-t', '--target', help='DEPRECATED.  Use --solution instead.')

    subparser = subparsers.add_parser('altbuild', help='Build the current solution(s) with the alternate build system.')
    subparser.set_defaults(func=subcommand_altbuild)
    subparser.add_argument('-s', '--solution', help= \
        'Select the solution(s) to build. Select multiple solutions as a comma separated list with no spaces. Leave empty to build ALL solutions in the following order: \
        ' + get_build_solutions(data)
    )
    subparser.add_argument('-p', '--project', help='Specify the project to build within a solution.')
    subparser.add_argument('-l', '--language', help='Specify the one language to build.  Leave empty to build ALL languages in the following order: C++,C#,Publish')
    subparser.add_argument('-r', '--remaining', action='store_true', default=False, help='Build all remaining solutions after the selected solution.')
    subparser.add_argument('-k', '--keepgoing', action='store_true', default=False, help='Continue building other build graphs even if one fails.')
    subparser.add_argument('-c', '--cleantests', action='store_true', default=False, help='Clean and republish the tests output directory.')
    subparser.add_argument('-t', '--target', help='DEPRECATED.  Use --solution instead.')

    subparser = subparsers.add_parser('scons_clean', help='Remove all scons build output for the current build variant')
    subparser.set_defaults(func=subcommand_clean)
    subparser.add_argument('-f', '--force', action='store_true', default=False, help='Force a clean of the output directory.')
    subparser.add_argument('-a', '--all', action='store_true', default=False, help='Also clean the perforce managed input directory.')
    subparser.add_argument('-r', '--reports', action='store_true', default=False, help='Also clean the coverage reports directory.')
    subparser.add_argument('-l', '--lockserver', action='store_true', default=False, help='Also clean the lock server directory.')
    subparser.add_argument('-s', '--solution', help= \
        'Select the solution(s) to clean.  Not currently supported by SCAScons based solutions.'
    )

    subparser = subparsers.add_parser('prebuilt', help='Prime the output with a mod.  Supports changes to the component BOM.')
    subparser.set_defaults(func=subcommand_prebuilt)
    subparser.add_argument('-f', '--force', action='store_true', default=False, help='Force a clean of the output directory.')
    subparser.add_argument('-u', '--uselocal', action='store_true', default=False, help='Use the previously downloaded mod zip, if available.')
    subparser.add_argument('-b', '--build', help='Specify the pipeline build ID.  Defaults to the latest.')
    subparser.add_argument('-c', '--commit', help='Specify the GIT commit ID.')
    subparser.add_argument('-s', '--sync', action='store_true', default=False, help='Create a local branch based forked from the same commit ID.')
    subparser.add_argument('-m', '--mod_variant', default="vtune", help='Specify the mod variant to download.  Defaults to vtune.')
    subparser.add_argument('-a', '--all', action='store_true', default=False, help='Also clean the perforce managed input directory.')
    subparser.add_argument('-r', '--reports', action='store_true', default=False, help='Also clean the coverage reports directory.')
    subparser.add_argument('-l', '--lockserver', action='store_true', default=False, help='Also clean the lock server directory.')
    subparser.add_argument('-k', '--brokenbuild', action='store_true', default=False, help='Specified changelist is a broken build.')
    subparser.add_argument('-n', '--nopdb', action='store_true', default=False, help='Skip downloading the PDB files.  Cannot be used with --onlypdb.')
    subparser.add_argument('-o', '--onlypdb', action='store_true', default=False, help='Only download the PDB files.  Cannot be used with --nopdb.')

    subparser = subparsers.add_parser('snapshot', help='Prime the output with a mod.  Does NOT support changes to the component BOM.')
    subparser.set_defaults(func=subcommand_snapshot)
    subparser.add_argument('-f', '--force', action='store_true', default=False, help='Force a clean of the output directory.')
    subparser.add_argument('-u', '--uselocal', action='store_true', default=False, help='Use the previously downloaded mod zip, if available.')
    subparser.add_argument('-b', '--build', help='Specify the pipeline build ID.  Defaults to the latest.')
    subparser.add_argument('-c', '--commit', help='Specify the GIT commit ID.')
    subparser.add_argument('-s', '--sync', action='store_true', default=False, help='Create a local branch based forked from the same commit ID.')
    subparser.add_argument('-m', '--mod_variant', default="vtune", help='Specify the mod variant to download.  Defaults to vtune.')
    subparser.add_argument('-a', '--all', action='store_true', default=False, help='Also clean the perforce managed input directory.')
    subparser.add_argument('-r', '--reports', action='store_true', default=False, help='Also clean the coverage reports directory.')
    subparser.add_argument('-l', '--lockserver', action='store_true', default=False, help='Also clean the lock server directory.')
    subparser.add_argument('-k', '--brokenbuild', action='store_true', default=False, help='Specified changelist is a broken build.')
    subparser.add_argument('-n', '--nopdb', action='store_true', default=False, help='Skip downloading the PDB files.  Cannot be used with --onlypdb.')
    subparser.add_argument('-o', '--onlypdb', action='store_true', default=False, help='Only download the PDB files.  Cannot be used with --nopdb.')

    subparser = subparsers.add_parser('prebuilttests', help='Prime the output with the tests.')
    subparser.set_defaults(func=subcommand_prebuilttests)
    subparser.add_argument('-f', '--force', action='store_true', default=False, help='Force a clean of the Tests directory.')
    subparser.add_argument('-u', '--uselocal', action='store_true', default=False, help='Use the previously downloaded mod zip, if available.')
    subparser.add_argument('-b', '--build', help='Specify the pipeline build ID.  Defaults to the latest.')
    subparser.add_argument('-c', '--commit', help='Specify the GIT commit ID.')
    subparser.add_argument('-s', '--sync', action='store_true', default=False, help='Create a local branch based forked from the same commit ID.')
    subparser.add_argument('-m', '--mod_variant', default="vtune", help='Specify the mod variant to download.  Defaults to vtune.')
    subparser.add_argument('-k', '--brokenbuild', action='store_true', default=False, help='Specified changelist is a broken build.')

    subparser = subparsers.add_parser('cache_helpmedia', help='Force cache helpmedia into the local component cache.  These files can be large.')
    subparser.set_defaults(func=subcommand_cachehelpmedia)

    subparser = subparsers.add_parser('runhelloapp', help='Run HELLOAPP')
    subparser.set_defaults(func=subcommand_runhelloapp)

    subparser = subparsers.add_parser('runhelloapptest', help='Run HELLOAPP with a dev license')
    subparser.set_defaults(func=subcommand_runhelloapptest)

    subparser = subparsers.add_parser('rungendes', help='Run GenDes')
    subparser.set_defaults(func=subcommand_rungendes)

    subparser = subparsers.add_parser('rungendestest', help='Run GenDes with a dev license')
    subparser.set_defaults(func=subcommand_rungendestest)
    
    subparser = subparsers.add_parser('runadams', help='Run Adams')
    subparser.set_defaults(func=subcommand_runadams)

    subparser = subparsers.add_parser('runadamstest', help='Run Adams with a dev license')
    subparser.set_defaults(func=subcommand_runadamstest)

    subparser = subparsers.add_parser('rungdengine', help='Run GD Engine')
    subparser.set_defaults(func=subcommand_rungdengine)

    subparser = subparsers.add_parser('rungdenginetest', help='Run GD Engine with a dev license')
    subparser.set_defaults(func=subcommand_rungdenginetest)

    subparser = subparsers.add_parser('runapex', help='Run Apex')
    subparser.set_defaults(func=subcommand_runapex)

    subparser = subparsers.add_parser('runapextest', help='Run Apex with a dev license')
    subparser.set_defaults(func=subcommand_runapextest)

def app_specific_sandbox_data(data):
    variant_dir = _get_variant_dir(data)

    data.local['clef_dir'] = data.local['mod_dir'] + '/clef'
    data.local['glef_dir'] = data.local['mod_dir'] + '/glef'
    data.local['gendes_dir'] = data.local['mod_dir'] + '/gendes'
    data.local['adams_dir'] = data.local['mod_dir'] + '/adams'
    data.local['apex_dir'] = data.local['mod_dir'] + '/apex'

    data.local['apex_components_dir'] = data.local['apex_dir'] + '/Components'

    data.local['sca_object_dir'] = variant_dir + '/obj'
    # Frequently used subdirectories for build outputs
    data.local['leaf_appframe_dir'] = data.local['leaf_dir'] + '/Framework' + '/AppFrame'
    data.local['car_dir'] = data.local['apex_components_dir'] + '/headlessAdams'
    data.local['alternate_build_requested'] = False
    return data

def app_specific_env(data):
    data = compute_compiler(data)
    variant_dir = _get_variant_dir_env_variable(data)
    workspace_output_root = _get_workspace_output_root_env_variable(data)

    data.env['APEX_BIN_DIR'] = os.path.join(variant_dir, 'mod', 'leaf', 'Framework', 'AppFrame', 'WIN8664', 'bin')
    data.env['CLEF_DIR'] = os.path.join(variant_dir, 'mod', 'clef')
    data.env['GLEF_DIR'] = os.path.join(variant_dir, 'mod', 'glef')
    data.env['HELLOAPP_DIR'] = os.path.join(variant_dir, 'mod', 'helloapp')
    data.env['GENDES_DIR'] = os.path.join(variant_dir, 'mod', 'gendes')
    data.env['ADAMS_DIR'] = os.path.join(variant_dir, 'mod', 'adams')

    data.env['APP_DIR'] = os.path.join(variant_dir, 'mod', 'apex')
    data.env['ADAMSCAR_RUNTIME'] = os.path.join(data.env['APP_DIR'], 'Components', 'headlessAdams')
    data.env['NUGET_RUNTIME'] = os.path.join(workspace_output_root, 'components', 'nuget')
    
    dag_roots = get_compilation_roots(data)
    for dag_alias, values in list(dag_roots.items()):
        delivery_alias, unused0, unused1, dag_runtime_path, dag_bindir_path, unused3, unused4, unused5, unused6 = values
        if delivery_alias == 'clef' or delivery_alias == 'glef':
            delivery_alias = 'leaf'
        data.local[dag_alias.lower() + '_runtime'] = os.path.normpath(os.path.join(data.local['mod_dir'], delivery_alias, dag_runtime_path))
        data.env[dag_alias.upper() + '_RUNTIME'] = os.path.normpath(os.path.join(data.env['MOD_DIR'], delivery_alias, dag_runtime_path))

    #GSC
    data.env['GSC_Parasolid_VERSION'] = 'V30.0.198'
    data.env['GSC_BOOST_VERSION'] = 'V1.60.0'
    data.env['GSC_LOG_SWITCH'] = 'GSC_LOG_OFF'            # if you want to enable GSC log, set GSC_LOG_ON, else set GSC_LOG_OFF.
    data.env['GSC_USER_LOG_SWITCH'] = 'GSC_USER_LOG_ON'        # if you want to enable GSC user log, set GSC_USER_LOG_ON, else set GSC_USER_LOG_OFF.
    # If you want to enable GSC test case automatic generate, set to GSC_BUILD_TESTCASE_AUTO_GENERATE, else set to GSC_NO_BUILD_TESTCASE_AUTO_GENERATE.
    # The default value must be not to build test case automatic generate related code. Because if open it, it will make code coverage lower and add many unused code into release version GSC.
    # If you want to generate test case, enable following line command temporary.
    data.env['GSC_TESTCASE_AUTO_GENERATE_SWITCH'] = 'GSC_NO_BUILD_TESTCASE_AUTO_GENERATE'

    ## These are additional variables used by SConopts/Sconscript files
    data.env['GeomTranslation_RUNTIME'] = os.path.join(data.env['LEAF_DIR'], 'Components', 'GeomTranslation')
    data.env['CTC_INCLUDE'] = os.path.join(data.env['APP_DIR'], 'Services', 'CTC', 'apps', 'include')
    data.env['GEN_TESTS_RUNTIME'] = os.path.join(variant_dir, 'tests', 'GEN', 'apps')

    #DGK
    data.env['VTK_VERSION'] = 'V8.0.0'

    ## BEGIN Deprecated environment variables
    # They should be moved to data.local when possible.

    data.env['APPLICATION_TOP'] = data.env['CLEF_DIR']

    data.env['CODELINE'] = apex_info.get_branch()
    data.env['SCA_VERSION'] = apex_info.get_scaversion()
    data.env['PRED_EDITION'] = apex_info.getPredEdition()
    data.env['PRED_RELEASE'] = apex_info.getPredRelease()

    data.env['GSC_THIRDPARTY_DIR'] = os.path.join(data.env['LEAF_DIR'], 'Services', 'GSC', 'ThirdParty')
    data.env['MGC_THIRDPARTY_DIR'] = os.path.join(data.env['APP_DIR'], 'Services', 'MGC', 'ThirdParty')
    ## END Deprecated environment variables

    data.env['SCATOOLS_RUNTIME'] = os.path.join(workspace_output_root, 'components', 'scatools')
    data.env['SCASYSTEM_RUNTIME'] = os.path.join(data.env['LEAF_DIR'], 'Components', 'scasystem')
    
    # some SCA Environment variables have failed some parts of our builds
    # so we clear them here
    data.env['SCA_SERVICE_CATALOG'] = ""
    data.env['SCA_REMOTING_SDC'] = ""
    data.env['SCABASE'] = ""
    data.env['SCAMACH'] = ""

    # HeadlessAdams
    data.env['HEADLESSADAMS_RUNTIME'] = os.path.join(os.path.join(data.env['APP_DIR'], 'components', 'headlessAdams'))

    return data

def compute_app_specific_path(data, path_data):
    sca_resource_dir = ''

    path_data['PATH1']       += '%WORKSPACE_INPUT_ROOT%\\tools;'
    path_data['PATH1']       += '%WORKSPACE_INPUT_ROOT%\\tools\\gnuwin32\\bin;'
    path_data['PATH1']       += '%ProgramFiles%\\Git\\cmd;'
    path_data['PATH1']       += '%ProgramFiles%\\Git LFS;'
    path_data['PATH1']       += '%ProgramFiles%\\Scalar;'
    path_data['PATH1']       += '%WORKSPACE_OUTPUT_ROOT%\\components\\cppcheck\\WIN8664;'
    path_data['PATH1']       += '%WORKSPACE_INPUT_ROOT%\\tools\\azcopy;'
    path_data['PATH1']       += '%WORKSPACE_INPUT_ROOT%\\tools\\7-Zip;'
    path_data['PATH1']       += '%WORKSPACE_INPUT_ROOT%\\tools\\OpenCppCoverage;'
    path_data['PATH1']       += '%WORKSPACE_INPUT_ROOT%\\tools\\CodeCoverageToXml;'
    path_data['PATH1']       += '%WORKSPACE_INPUT_ROOT%\\tools\\ReportGenerator;'
    path_data['PATH1']       += '%WORKSPACE_OUTPUT_ROOT%\\components\\sccache;'
    path_data['PYTHONPATH'] += '%WORKSPACE_INPUT_ROOT%\\tools\\testrunner\\bin;'
    path_data['PYTHONPATH'] += '%WORKSPACE_INPUT_ROOT%\\tools\\component_cache\\noarch;'
    path_data['PYTHONPATH'] += '%WORKSPACE_INPUT_ROOT%\\tools\\scascons;'
    path_data['PYTHONPATH'] += '%WORKSPACE_INPUT_ROOT%\\tools\\csharp;'
    path_data['PYTHONPATH'] += '%SCASYSTEM_RUNTIME%\\lib\\python;'
    path_data['PYTHONPATH'] += '%APPFRAME_RUNTIME%\\lib\\python3;'
    path_data['PYTHONPATH'] += '%SCATOOLS_RUNTIME%\\RunTime\\lib\\python\\SCASCons;'
    path_data['PYTHONPATH'] += '%MOD_DIR%\\python3\\Lib\\site-packages;'
    path_data['PYTHONPATH'] += '%WORKSPACE_INPUT_ROOT%\\tools\\lib_py\\python3;'

    # Non-SCA libraries are in the WIN8664\lib directory of these components
    components_nonsca = (\
                'scasystem', \
                'adamscar', \
                'headlessadams', \
                )

    # Non-SCA libraries are in the WIN8664\lib directory of these services
    services_nonsca = (\
                'eom', \
                'aem', \
                'gsc', \
                'gen', \
                'muc', \
                'mgc', \
                'post', \
                'thd', \
                'motion', \
                'spf', \
                )

    # Only SCA libraries are in the WIN8664\lib directory of these services
    services_sca = (\
                'ctc', \
                'dgk', \
                'ddm', \
                'ftc', \
                'mqc', \
                'acs', \
                'vtk_wrapper', \
                )

    # Non-SCA libraries are in the WIN8664\lib directory of these plugins
    plugins_nonsca = (\
                'charting_plugin', \
                'fem_plugin', \
                'demo_plugin', \
                'modeling_plugin', \
                'motion_plugin', \
                'post_plugin', \
                'thd_plugin', \
                )

    # Only SCA libraries are in the WIN8664\lib directory of these plugins
    plugins_sca = (\
                'geom_plugin', \
                'measure_plugin', \
                'transform_plugin', \
                'midsurf_plugin', \
                'geomdebug_plugin', \
                'core_plugin', \
                'base_plugin', \
                'shell_plugin', \
                'display_plugin', \
                'adams_plugin', \
                )

    plugins_leaf = (\
                'CorePlugin', \
                'BasePlugin', \
                'ShellPlugin', \
                'DisplayPlugin', \
                'MeasurePlugin', \
                'MidsurfPlugin', \
                'TransformPlugin', \
                'GeomPlugin', \
                'GeomDebugPlugin', \
                'FEMPlugin', \
                )

    plugins_apex = (\
                'DemoPlugin', \
                'PostPlugin', \
                'THDPlugin', \
                'MotionPlugin', \
                'ModelingPlugin', \
                'AdamsPlugin', \
                'ChartingPlugin', \
                )

    dag_roots = get_compilation_roots(data)

    # Windows library paths added to PATH
    # ===================================
    path_data['PATH2'] += data.env['LEAF_DIR'] + '\\Components\\shared\\lib;'
    path_data['PATH2'] += data.env['SCATOOLS_RUNTIME'] + ';'
    path_data['PATH2'] += data.env['LEAF_DIR'] + '\\Components\\parasolid\\WIN8664;'
    path_data['PATH2'] += data.env['LEAF_DIR'] + '\\Components\\VTK\\WIN8664;'

    # Required for SCAKernel_##.dll
    path_data['PATH2'] += data.env['SCASYSTEM_RUNTIME'] + '\\WIN8664\\lib;'

    # Required for ServiceCacheTestSupport.dll
    sca_resource_dir += data.env['TESTSUPPORT_RUNTIME'] + '\\res;'
    path_data['PATH2'] += data.env['TESTSUPPORT_RUNTIME'] + '\\WIN8664\\lib;'

    # The framework paths are degenerate, no loop necessary
    sca_resource_dir += data.env['APPFRAME_RUNTIME'] + '\\res;'
    path_data['PATH2'] += data.env['APPFRAME_RUNTIME'] + '\\WIN8664\\bin;'
    path_data['PATH2'] += data.env['APPFRAME_RUNTIME'] + '\\WIN8664\\lib;'

    for row in components_nonsca:
        if row.upper() == 'ADAMSCAR':
            path_data['PATH2'] += data.env[row.upper() + '_RUNTIME'] + '\\release\\win64;'
        else:
            sca_resource_dir += data.env[row.upper() + '_RUNTIME'] + '\\res;'
            path_data['PATH2'] += data.env[row.upper() + '_RUNTIME'] + '\\WIN8664\\lib;'

    for row in services_nonsca:
        sca_resource_dir += data.env[row.upper() + '_RUNTIME'] + '\\res;'
        # Skip adding to PATH when the non-SCA DLLs are already in PATH.
        if dag_roots[row][4] != 'Framework/AppFrame':
            path_data['PATH2'] += data.env[row.upper() + '_RUNTIME'] + '\\WIN8664\\lib;'

    for row in plugins_nonsca:
        sca_resource_dir += data.env[row.upper() + '_RUNTIME'] + '\\res;'
        # Skip adding to PATH when the non-SCA DLLs are already in PATH.
        path_data['PATH2'] += data.env[row.upper() + '_RUNTIME'] + '\\WIN8664\\lib;'

    # SCA library paths added to SCA_LD_LIBRARY_PATH
    # ==============================================
    sca_resource_dir += data.env['TESTSUPPORT_CS_RUNTIME'] + '\\res;'
    path_data['SCA_LD_LIBRARY_PATH'] += data.env['TESTSUPPORT_CS_RUNTIME'] + '\\WIN8664\\lib;'#SCA_LD_LIBRARY_PATH?

    sca_resource_dir += data.env['UISERVICES_RUNTIME'] + '\\res;'
    path_data['SCA_LD_LIBRARY_PATH'] += data.env['UISERVICES_RUNTIME'] + '\\WIN8664\\lib;'#SCA_LD_LIBRARY_PATH?

    for row in services_sca:
        sca_resource_dir += data.env[row.upper() + '_RUNTIME'] + '\\res;'
        # Skip adding to SCA_LD_LIBRARY_PATH when the non-SCA DLLs are already in PATH.
        if dag_roots[row][4] != 'Framework/AppFrame':
            path_data['SCA_LD_LIBRARY_PATH'] += data.env[row.upper() + '_RUNTIME'] + '\\WIN8664\\lib;'

    for row in plugins_sca:
        sca_resource_dir += data.env[row.upper() + '_RUNTIME'] + '\\res;'
        # Skip adding to PATH when the non-SCA DLLs are already in PATH.
        path_data['SCA_LD_LIBRARY_PATH'] += data.env[row.upper() + '_RUNTIME'] + '\\WIN8664\\lib;'

    # ==========================================
    for xruntime in plugins_leaf:
        sca_resource_dir += os.path.join(data.env['LEAF_DIR'], 'Plugins', xruntime, 'res;')

    for xruntime in plugins_apex:
        sca_resource_dir += os.path.join(data.env['APP_DIR'], 'Plugins', xruntime, 'res;')

    # add path to HelloPlugin res folder so stest run from remoting can find it's types
    sca_resource_dir += os.path.join(data.env['HELLOAPP_DIR'], 'Plugins', 'HelloPlugin', 'SCA_Services', 'res;')

    sca_resource_dir += data.env['GeomTranslation_RUNTIME'] + '\\res;'

    data.env['SCA_RESOURCE_DIR'] = sca_resource_dir
    data.env['SCA_CATALOG_DIR'] = sca_resource_dir
    data.env['SCA_LD_LIBRARY_EXTEND'] = "1";
    return data, path_data

def compute_compiler(data):
    if data.local['is_linux'] == True:
        data.env_linux['CXX'] = 'icpc'
        data.env_linux['CC'] = 'icc'
        data.env_linux['FC']='ifort'
    else: # Windows
        data.env['CXX'] = 'cl.exe'
        data.env['CC'] = 'cl.exe'
    return data

def _compute_scons_build_options(data):
    scons_build_options = '-j' + str(data.options['num_jobs'])
    scons_build_options += ' decider=md5-timestamp --implicit-deps-changed'
    scons_build_options += ' --minidltypes MSVSPROJECTS=yes'
    scons_build_options += ' STRICT_CHECK=True'
    scons_build_options += ' FCOMPILER="None"'
    scons_build_options += ' --disableSConoptsUser'
    if data.options['verbosity'] == 0:
        scons_build_options += ' COMMANDPRINT="None"'
    elif data.options['verbosity'] == 1:
        scons_build_options += ' --debug=explain'
        scons_build_options += ' COMMANDPRINT="None"'
    else:
        scons_build_options += ' --debug=explain --debug=time'
        scons_build_options += ' COMMANDPRINT="Full"'
    scons_build_options += ' INTEL_FORTRAN_VERSION=' + data.local['intel_compiler_version_scons']
    scons_build_options += ' MIN_INTEL_FORTRAN_VERSION=' + data.local['intel_compiler_version_scons']
    scons_build_options += ' MAX_INTEL_FORTRAN_VERSION=' + data.local['intel_compiler_version_scons']
    if data.local['is_linux'] == False:
        # MSVS_VERSION=14.1 specifies to use vcvarsall.bat from Visual Studio 2017.
        scons_build_options += ' MSVS_VERSION=14.1 MIN_MSVS_VERSION=14.1 MAX_MSVS_VERSION=14.1'
        scons_build_options += ' VCVARS_ARGS="""10.0.18362.0 -vcvars_ver=14.16.27023"""'
    else:
        scons_build_options += ' INTEL_CXX_VERSION=' + data.local['intel_compiler_version_scons']

    if data.local['is_linux'] == False:
      # warning C4251: class '<>' needs to have dll-interface to be used by clients of class '<>'
      # warning C4275: non dll-interface class '<>' used as base for dll-interface class '<>' : see declaration of '<>'
      # warning C4917: '<>': a GUID can only be associated with a class, interface or namespace
      # warning C5026: '<>': move constructor was implicitly defined as deleted
      # warning C5027: '<>': move assignment operator was implicitly defined as deleted
      # warning C4819: The file contains a character that cannot be represented in the current code page (936). Save the file in Unicode format to prevent data loss
      # -WX in the CPPFLAGS causes all warnings to be errors
      scons_build_options += ' CPPFLAGS="-Gw -Gy -bigobj -W3 -WX -wd4251 -wd4275 -wd4917 -wd5026 -wd5027 -wd4819 -DBOOST_CONFIG_SUPPRESS_OUTDATED_MESSAGE"'

      #TEMPORARY: 4996 to suppores ::tr1 warnings
      #TEMPORARY: warning C4774: 'swprintf_s' : format string expected in argument 3 is not a string literal
      #TEMPORARY: error C4596: '{ctor}': illegal qualified name in member declaration
      #TEMPORARY: warning C5038: data member 'msc::apex::ogreext::GlslHandle::m_resized' will be initialized after data member 'msc::apex::ogreext::GlslHandle::m_beginPick'
      #TEMPORARY: warning C5039: 'TpSetCallbackCleanupGroup': pointer or reference to potentially throwing function passed to extern C function under -EHc. Undefined behavior may occur if this function throws an exception.
      scons_build_options += ' LINKFLAGS="-OPT:REF -OPT:ICF"'

    scons_build_options += ' BOOST_SYSTEM=' + data.local['boost_dir']
    scons_build_options += ' GOOGLETEST_SYSTEM=' + data.local['gtest_dir']
    scons_build_options += ' GOOGLEBTREE_SYSTEM=' + data.local['btree_dir']
    optional_mkl = ''
    if data.machine.get('visual_studio_unavailable', False) != True:
        optional_mkl = ' INTELMKL_SYSTEM="\"' + data.local['intelmkl_dir'] + '\""'
    if data.local['is_linux'] == True:
        optional_mkl = ' INTELMKL_SYSTEM=' + data.local['intelmkl_dir']
    scons_build_options += optional_mkl
    scons_build_options += ' HDF5_SYSTEM=' + data.local['hdf5_dir']
    scons_build_options += ' SEPARATEOBJBYDIR="yes"'
    scons_build_options += ' SCA_OBJECT=' + data.local['sca_object_dir']
    scons_build_options += ' SCACATALOG="split_by_component"'
    scons_build_options += ' ADAMSCAR_SYSTEM=' + data.local['car_dir']

    if data.local['SKIPTESTEXECUTION'] == 'True':
        scons_build_options += ' SKIPTESTEXECUTION=True'

    if data.options['build_variant'] == data.local['release_name']:
       data.local['scons_build_options'] = scons_build_options + ' CPPDEFINES=NDEBUG BUILDTYPE=opt VTUNEBUILD=true'
    elif data.options['build_variant'] == data.local['vtune_name']:
       data.local['scons_build_options'] = scons_build_options + ' BUILDTYPE=opt VTUNEBUILD=true'
    elif data.options['build_variant'] == data.local['debug_name']:
       scons_build_options += ' BUILDTYPE=debug'
       if data.local['is_linux'] == False:
           scons_build_options += ' LINKFLAGS="-PROFILE -OPT:REF -OPT:ICF"'
       data.local['scons_build_options'] = scons_build_options
    return data

def subcommand_altbuild(parser, args, subargs, data):
    data.local['alternate_build_requested'] = True
    return subcommand_build(parser, args, subargs, data)

def subcommand_build(parser, args, subargs, data):
    if data.machine.get('visual_studio_unavailable', False) == True:
        print("ERROR: 'sand build' is not supported on machines which have 'visual_studio_unavailable' set to true.")
        return 1

    print('################################################################')
    print('### Build requested ############################################')
    print('################################################################')

    shouldBuildRemaining = vars(args)['remaining']
    shouldKeepGoing = vars(args)['keepgoing']
    didErrorOccur = False
    options_string = " ".join(subargs)

    solution_list = vars(args)['solution']
    # This is to support the deprecated --target option.
    if solution_list == None:
        solution_list = vars(args)['target']

    if not checkSolutionsValidBuild(args, data):
        print("ERROR: Selected solution(s) of '" + solution_list + "' is not valid.  Please run 'sand build --help' to see the complete list of valid solutions.")
        return 1

#    if checkScriptingTestsForSleep(data):
#       return 1
    
#    if checkForColorCodes(data):
#       return 1

    if (vars(args)['cleantests']):
        _clean_tests(parser, args, subargs, data)

    if isComponentCacheEnabled(data):
        status = _cache_comp(parser, args, subargs, data)
        if status != 0: return status

    dag_roots = get_compilation_roots(data)

    hasBuiltOneSolution = False
    dag_max = len(dag_roots)
    dag_current = 1
    if solution_list != None:
        solution_list = solution_list.split(',')
    for dag_alias, values in list(dag_roots.items()):
        dag_delivery_alias, dag_action, dag_input_path, dag_runtime_path, dag_bindir_path, dag_should_gen_sln, dag_sln, dag_options, dag_lang = values
        if solution_list == None or dag_alias in solution_list or shouldBuildRemaining and hasBuiltOneSolution:
            language = vars(args)['language']
            if language == None or language.lower() == dag_lang.lower():
                start_time = datetime.now()
                message = '### Building ' + str(dag_current).zfill(2) + ' of ' + str(dag_max) + ' '
                message += '### ' + dag_alias + ' (' + dag_lang + ') '
                message += "#" * (64 - len(message))

                if data.local['is_linux'] == False:
                    _call_command(data, 'title ' + message, True)
                print('################################################################')
                print(message)
                print('################################################################')

                if (data.local['alternate_build_requested']):
                    if dag_action.__name__ == "blast_build":
                        dag_action = scons_build
                    elif dag_action.__name__ == "scons_build":
                        dag_action = blast_build

                status = dag_action(data, args, options_string, dag_alias, values)
                _warn_on_long_workspace_path(data)
                if status != 0:
                    if shouldKeepGoing:
                        print('ERROR: Build Error Occurred: ' + message)
                        print('Keep going is enabled.')
                        didErrorOccur = True
                    else:
                        print('ERROR: Build Error Occurred: ' + message)
                        return status

                hasBuiltOneSolution = True
                end_time = datetime.now()
                duration = end_time - start_time
                message = '### Finished ' + str(dag_current).zfill(2) + ' of ' + str(dag_max) + ' '
                message += '### ' + dag_alias + ' (' + dag_lang + ') '
                message += "#" * (64 - len(message))
                if data.local['is_linux'] == False:
                    _call_command(data, 'title ' + message, True)
                duration = '### Duration: ' + str(duration) + ' (' + str(duration.total_seconds()) + ' seconds) '
                duration += "#" * (64 - len(duration))
                print('################################################################')
                print(message)
                print(duration)
                print('################################################################')
                print('')

        dag_current += 1
    if didErrorOccur:
        print('################################################################')
        print('### Build ERROR occured ########################################')
        print('### But --keepgoing option was specified. ######################')
        print('################################################################')
        return 1
    else:
        print('################################################################')
        print('### Build successful ###########################################')
        print('################################################################')
    return 0

def subcommand_ide(parser, args, subargs, data):
    if data.machine.get('visual_studio_unavailable', False) == True:
        print("ERROR: 'sand ide' is not supported on machines which have 'visual_studio_unavailable' set to true.")
        return 1

    if isComponentCacheEnabled(data):
        status = _cache_comp(parser, args, subargs, data)
        if status != 0: return status


    options_string = " ".join(subargs)

    solution_list = vars(args)['solution']
    # This is to support the deprecated --target option.
    if solution_list == None:
        solution_list = vars(args)['target']

    if solution_list is None:
        print("ERROR: No solution specified.  Please run 'sand ide --help' to see the complete list of valid solutions.")
        return 1
    if not checkSolutionsValidIDE(args, data):
        print("ERROR: Selected solution of '" + solution_list + "' is not valid.  Please run 'sand ide --help' to see the complete list of valid solutions.")
        return 1
    dag_roots = get_compilation_roots(data)
    dag_roots = append_RelativeProject_roots(dag_roots)
    solution_list = solution_list.split(',')
    for dag_alias, values in list(dag_roots.items()):
        dag_delivery_alias, dag_action, dag_input_path, dag_runtime_path, dag_bindir_path, dag_should_gen_sln, dag_sln, dag_options, dag_lang = values
        dag_bindir_path = dag_bindir_path or dag_runtime_path
        solution_file = os.path.abspath(os.path.join(data.local['input_tree'], dag_input_path, dag_sln))
        if dag_alias in solution_list:
            # First generate the solution file if necessary.
            if (dag_action.__name__ == 'blast_build' or (dag_action.__name__ == 'conditional_build' and data.local['is_linux'] == False)) and dag_lang == 'C++':
                blast_ide_dir = os.path.join(data.local['output_tree'],data.local['variants_dir_name'],data.options['build_variant'],'ide',dag_alias)
                solution_file = blast_ide_dir + '/' + dag_alias + '.sln'
            elif (dag_should_gen_sln == True) and not os.path.exists(solution_file):
                root_path = data.local['input_tree'] + '/' + dag_input_path
                os.chdir(root_path+"")
                data = _compute_scons_build_options(data)
                dag_options = dag_options.replace(' UNITYBUILD', '') # Remove Blast only build option. #TODO refactor into helper function.
                scons_exe = data.local['output_components_dir'] + '/scatools/scons'
                command = scons_exe + ' ' + data.local['scons_build_options'] + ' CLEAROLDIDL=' + dag_lang + ' ' + dag_options + ' MSVSPROJECTS=yes msvs ' + options_string
                status = _call_command(data, command)
                if status != 0:
                    print("ERROR: Unable to generate the IDE for solution '" + dag_alias + "'")
                    return status
                # Retry loop to work around Windows race condition:
                # https://blogs.msdn.microsoft.com/oldnewthing/20120907-00/?p=6663/
                giveUpCounter = 8
                while giveUpCounter > 0:
                    if os.path.exists(solution_file):
                        break
                    giveUpCounter -= 1
                    time.sleep(1)

            # Now launch the solution.
            _warn_on_long_workspace_path(data)
            command = 'devenv ' + solution_file + ' ' + options_string
            if not os.path.exists(solution_file):
                print('ERROR: Unable to open solution file of ' + solution_file + ', which does not exist. Try building the solution before attempting to open the solution file.')
                return 1
            if data.options['verbosity'] == 2: print(command)
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(command, shell=True, stdin=None, stdout=None, stderr=None, close_fds=True, creationflags=DETACHED_PROCESS)
    return 0

def subcommand_clean(parser, args, subargs, data):
    solution_list = vars(args)['solution']
    if solution_list == None:
        clean_ide(data)
        _clean_variant(parser, args, subargs, data);
        return

    solution_list = solution_list.split(',')
    dag_roots = get_compilation_roots(data)
    dag_max = len(dag_roots)
    dag_current = 1
    for dag_alias, values in list(dag_roots.items()):
        dag_delivery_alias, dag_action, dag_input_path, dag_runtime_path, dag_bindir_path, dag_should_gen_sln, dag_sln, dag_options, dag_lang = values
        if dag_alias in solution_list:
            message = '### Cleaning ' + str(dag_current).zfill(2) + ' of ' + str(dag_max) + ' ### ' + dag_alias + ' (' + dag_lang + ') '
            message += "#" * (64 - len(message))
            if data.local['is_linux'] == False:
                _call_command(data, 'title ' + message, True)
            _print_verbosity1('################################################################')
            print(message)
            _print_verbosity1('################################################################')
            if dag_action.__name__ == 'blast_build' or (dag_action.__name__ == 'conditional_build' and data.local['is_linux'] == False):
                clean_variant(data, dag_alias, dag_delivery_alias, dag_runtime_path)
            else:
                print('ERROR: The solution ' + dag_alias + ' does not support cleaning by itself.')
                return 1

def subcommand_prebuilt(parser, args, subargs, data):
    options_string = " ".join(subargs)
    if vars(args)['nopdb'] == True and vars(args)['onlypdb'] == True:
        print('ERROR: You cannot specify both --nopdb and --onlypdb.')
        return 1

    if vars(args)['force'] != True:
        print("##############################################################################")
        print("#           Are you sure you want to copy in a pre-built mod?                #")
        print("#                                                                            #")
        print("# This operation will delete ALL your previously built output files.         #")
        print("# Then it will locate the mod zip file on the network, copy, and extract it  #")
        print("# to your local output directory.  This can be useful if you only need to    #")
        print("# edit and rebuild a significant subset of the Predator depot.               #")
        print("#                                                                            #")
        print("# Usage: sand prebuilt -f [-u] [-p] [-c commit_id]                           #")
        print("#                                                                            #")
        print("# Arguments      Short  Default Value (based upon your current settings)     #")
        print("# =============  =====  =============                                        #")
        print("# --uselocal     -u     Use the local 7z file, download only if missing.     #")
        print("# --sync         -s     Sync the Git client to the same commit id.           #")
        print("#                                                                            #")
        print("# Example: 'sand prebuilt -ufsc 123456'                                      #")
        print("# Example: 'sand prebuilt -uf' (defaults to "+data.local['vtune_name']+" build of latest build id)#")
        print("#                                                                            #")
        print("# It is highly recommended to choose the latest commit id value which        #")
        print("# is earlier than your current commit id.                                    #")
        print("##############################################################################")
        return

    if data.machine.get('visual_studio_unavailable', False) == True:
        print("ERROR: 'sand prebuilt' is not supported on machines which have 'visual_studio_unavailable' set to true.")
        print("Use 'sand snapshot' instead.")
        return 1

    git_checkout_done = False

    if vars(args)['onlypdb'] == False:
        _clean_variant(parser, args, subargs, data)

        status, local_ZipFile, premod_label, git_commit_id = downloadModZip(parser, args, subargs, data)
        if status != 0: return status

        if vars(args)['sync'] == True:
            command = git_checkout_branch(git_commit_id)
            _call_command(data, command)
            git_checkout_done = True
        if status != 0: return status

        # The BOM may have changed during the above sync.  Update the_component_cache.
        status = the_component_cache.reinitialize()
        if status != 0: return status

        variant_dir = _get_variant_dir(data)
        # We need to bring in a SCA remoting python module,
        # which is built then published into the python2/lib/site-packages/ directory.
        command = data.local['7z_cmd'] + ' x -y -o' + variant_dir + ' -i!*/leaf/Components/python2/lib/site-packages/ ' + local_ZipFile
        status = _call_command(data, command)
        if status != 0: return status
        # We also need to bring other python3 modules, libraries, and headers.
        # Since there are many, we will just extract the entire component from the 7z file.
        command = data.local['7z_cmd'] + ' x -y -o' + variant_dir
        command += ' -x!*/apex/Documentation/UI/'
        command += ' -x!*/glef/Documentation/UI/'
        command += ' -x!*/clef/Documentation/UI/'
        command += ' ' + local_ZipFile
        status = _call_command(data, command)
        if status != 0: return status

    if vars(args)['nopdb'] == False and data.local['is_linux'] == False: # Linux doesn't have PDB files.
        status, local_ZipFile, premod_label, git_commit_id = downloadModZip(parser, args, subargs, data, '-pdb')
        if status != 0: return status

        if git_checkout_done == False:
            if vars(args)['sync'] == True:
                command = git_checkout_branch(git_commit_id)
                _call_command(data, command)
            if status != 0: return status

            # The BOM may have changed during the above sync.  Update the_component_cache.
            status = the_component_cache.reinitialize()
            if status != 0: return status

        variant_dir = _get_variant_dir(data)
        command = data.local['7z_cmd'] + ' x -y -o' + variant_dir + ' ' + local_ZipFile
        status = _call_command(data, command)
        if status != 0: return status

    status = _cache_comp(parser, args, subargs, data)
    if status != 0: return status

    status = _install_federated_database(data, data.local['eom_runtime'], args)
    if status != 0: return status

    _print_verbosity1("\nSuccessfully downloaded and extracted " + local_ZipFile)
    return status

def subcommand_snapshot(parser, args, subargs, data):
    options_string = " ".join(subargs)
    if vars(args)['nopdb'] == True and vars(args)['onlypdb'] == True:
        print('ERROR: You cannot specify both --nopdb and --onlypdb.')
        return 1

    if vars(args)['force'] != True:
        print("##############################################################################")
        print("#     Are you sure you want to use 'snapshot', instead of 'prebuilt'?        #")
        print("#                                                                            #")
        print("# Snapshot and prebuilt will both copy and extract a mod zipfile to your     #")
        print("# local output directory.  However, snapshot does not support changes to     #")
        print("# bom_apex.json.                                                             #")
        print("# If you need to modify bom_apex.json,                                       #")
        print("# either by manual edit, or by GIT sync, you should use prebuilt.            #")
        print("# Also, once your component cache is populated, prebuilt is usually much     #")
        print("# faster, since it does not have to re-extract all the components.  Also,    #")
        print("# prebuilt uses less disk space.                                             #")
        print("#                                                                            #")
        print("# Usage: sand snapshot -f [-u] [-p] [-c commit id]                           #")
        print("#                                                                            #")
        print("# Arguments      Short  Default Value (based upon your current settings)     #")
        print("# =============  =====  =============                                        #")
        print("# --uselocal     -u     Use the local 7z file, download only if missing.     #")
        print("# --sync         -s     Sync the Git client to the same commit id.           #")
        print("#                                                                            #")
        print("# Example: 'sand snapshot -ufsc 123456'                                      #")
        print("# Example: 'sand snapshot -uf' (defaults to "+data.local['vtune_name']+" build of latest commit id)#")
        print("#                                                                            #")
        print("# It is highly recommended to choose the latest commit id value which        #")
        print("# is earlier than your current commit id.                                    #")
        print("##############################################################################")
        return

    git_checkout_done = False
    if vars(args)['onlypdb'] == False:
        _clean_variant(parser, args, subargs, data)

        status, local_ZipFile, premod_label, git_commit_id = downloadModZip(parser, args, subargs, data)
        if status != 0: return status   

        if vars(args)['sync'] == True:
            command = git_checkout_branch(git_commit_id)
            _call_command(data, command)
            git_checkout_done = True
            if status != 0: return status

        variant_dir = _get_variant_dir(data)
        command = data.local['7z_cmd'] + ' x -y -o' + variant_dir + ' ' + local_ZipFile
        status = _call_command(data, command)
        if status != 0: return status

        if data.local['is_linux'] == False: # We do not build a component archive for Linux.
            status, local_ZipFile, premod_label, git_commit_id = downloadModZip(parser, args, subargs, data, '-comp')
            if status != 0: return status   

            command = data.local['7z_cmd'] + ' x -y -o' + variant_dir + ' ' + local_ZipFile
            status = _call_command(data, command)
            if status != 0: return status

    if vars(args)['nopdb'] == False and data.local['is_linux'] == False: # Linux doesn't have PDB files.
        status, local_ZipFile, premod_label, git_commit_id = downloadModZip(parser, args, subargs, data, '-pdb')
        if status != 0: return status

        if git_checkout_done == False:
            if vars(args)['sync'] == True:
                command = git_checkout_branch(git_commit_id)
                _call_command(data, command)
                if status != 0: return status

        variant_dir = _get_variant_dir(data)
        command = data.local['7z_cmd'] + ' x -y -o' + variant_dir + ' ' + local_ZipFile
        status = _call_command(data, command)
        if status != 0: return status

    disableComponentCache(data)
    for comp in the_component_cache.components:
        if not isComponentEnabled(data, comp):
            continue
        status = the_component_cache.cache_component(comp)
        if status != 0: return status

    status = _install_federated_database(data, data.local['eom_runtime'], args)
    if status != 0: return status

    _print_verbosity1("\nSuccessfully downloaded and extracted " + local_ZipFile)
    return status

def git_checkout_branch(git_commit_id):
    return 'git checkout -b branch_' + git_commit_id + ' ' + git_commit_id

def subcommand_prebuilttests(parser, args, subargs, data):
    options_string = " ".join(subargs)
    if vars(args)['force'] != True:
        print("##############################################################################")
        print("#           Are you sure you want to copy in a pre-test mod?                 #")
        print("#                                                                            #")
        print("# Usage: sand prebuilttests -f [-u] [-p] [-c CHANGELIST]                     #")
        print("#                                                                            #")
        print("# Arguments      Short  Current Value (based upon your current settings)     #")
        print("# ===========--  =====  =============                                        #")
        print("# --uselocal     -u     Use the local 7z file, download only if missing.     #")
        print("# --sync         -s     Sync the Git client to the same commit id.           #")
        print("#                                                                            #")
        print("# Example: 'sand prebuilttests -ufsc 123456'                                 #")
        print("# Example: 'sand prebuilttests -uf' (defaults to "+data.local['vtune_name']+" build of latest commit id)#")
        print("##############################################################################")
        return

    _print_verbosity1('Removing tests output directory: ' + data.local['tests_dir'])
    if os.path.isdir(data.local['tests_dir']):
        utilities.rmtree(data.local['tests_dir'])

    status, local_ZipFile, premod_label, git_commit_id = downloadModZip(parser, args, subargs, data, '-tests')
    if status != 0: return status

    if vars(args)['sync'] == True:
        command = 'git checkout ' + git_commit_id
        _call_command(data, command)
        if status != 0: return status

    variant_dir = _get_variant_dir(data)
    command = data.local['7z_cmd'] + ' x -y -o' + variant_dir + ' ' + local_ZipFile
    status = _call_command(data, command)
    if status != 0: return status

    _print_verbosity1("\nSuccessfully downloaded and extracted " + local_ZipFile)
    return status

def subcommand_cachehelpmedia(parser, args, subargs, data):
    _print_verbosity1('################################################################')
    print(            '### Caching/Publishing Help Media ##############################')
    _print_verbosity1('################################################################')
    enableComponentCache(data)
    output = {}
    status = the_component_cache.cache_component(alias = 'helpmedia', output_dict = output)
    if status != 0: return status
    if(output['was_updated']):
        status = clean_component(data, alias = 'helpmedia')
        if status != 0: return status
        status = publish_component(data, alias = 'help') #Must also publish "help" component when "helpmedia" is cleaned.
        if status != 0: return status
    status = publish_component(data, alias = 'helpmedia')
    if status != 0: return status
    return status

def subcommand_runhelloapp(parser, args, subargs, data):
    options_string = " ".join(subargs)
    command = data.local['mod_dir'] + '/runMSC_HelloApp.bat ' + options_string
    return _call_command(data, command)

def subcommand_runhelloapptest(parser, args, subargs, data):
    options_string = " ".join(subargs)
    command = data.local['mod_dir'] + '/runMSC_HelloAppTest.bat ' + options_string
    return _call_command(data, command)

def subcommand_rungendes(parser, args, subargs, data):
    options_string = " ".join(subargs)
    command = data.local['mod_dir'] + '/runMSC_GenDes.bat ' + options_string
    return _call_command(data, command)

def subcommand_rungendestest(parser, args, subargs, data):
    options_string = " ".join(subargs)
    command = data.local['mod_dir'] + '/runMSC_GenDesTest.bat ' + options_string
    return _call_command(data, command)
    
def subcommand_runadams(parser, args, subargs, data):
    options_string = " ".join(subargs)
    command = data.local['mod_dir'] + '/runMSC_Adams.bat ' + options_string
    return _call_command(data, command)

def subcommand_runadamstest(parser, args, subargs, data):
    options_string = " ".join(subargs)
    command = data.local['mod_dir'] + '/runMSC_AdamsTest.bat ' + options_string
    return _call_command(data, command)

def subcommand_rungdengine(parser, args, subargs, data):
    options_string = " ".join(subargs)
    command = data.local['mod_dir'] + '/runGD_Engine.bat ' + options_string
    return _call_command(data, command)

def subcommand_rungdenginetest(parser, args, subargs, data):
    options_string = " ".join(subargs)
    command = data.local['mod_dir'] + '/runGD_EngineTest.bat ' + options_string
    return _call_command(data, command)

def subcommand_runapex(parser, args, subargs, data):
    options_string = " ".join(subargs)
    command = data.local['mod_dir'] + '/runMSC_Apex.bat ' + options_string
    return _call_command(data, command)

def subcommand_runapextest(parser, args, subargs, data):
    options_string = " ".join(subargs)
    command = data.local['mod_dir'] + '/runMSC_ApexTest.bat ' + options_string
    return _call_command(data, command)

def subcommand_buildcache(parser, args, subargs, data):
    if not vars(args)['solution']: return 1
    os.environ['SCCACHE_DIR'] = os.path.join(data.machine['component_cache_root'], 'buildcache', 'sccache', vars(args)['solution'])
    command = 'sccache --show-stats'
    return subprocess.call(command)


def subcommand_buildcache_clean(parser, args, subargs, data):
    if not vars(args)['solution']: return 1
    cache_dir = os.path.join(data.machine['component_cache_root'], 'buildcache', 'sccache', vars(args)['solution'])
    os.environ['SCCACHE_DIR'] = cache_dir
    command = 'sccache --zero-stats'
    status = subprocess.call(command)
    utilities.rmtree(cache_dir)
    return status

def conditional_build(data, args, options_string, dag_alias, values):
    if (data.local['alternate_build_requested'] == True):
        if(data.local['is_linux'] == True):
            status = blast_build(data, args, options_string, dag_alias, values)
        else:
            status = scons_build(data, args, options_string, dag_alias, values)
    else:
        if(data.local['is_linux'] == True):
            status = scons_build(data, args, options_string, dag_alias, values)
        else:
            status = blast_build(data, args, options_string, dag_alias, values)
    return status

def conditional_idl_build(data, args, options_string, dag_alias, values):
    if (data.local['alternate_build_requested'] == True):
        if(data.local['is_linux'] == True):
            status = blast_idl_build(data, args, options_string, dag_alias, values)
        else:
            status = scons_build(data, args, options_string, dag_alias, values)
    else:
        if(data.local['is_linux'] == True):
            status = scons_build(data, args, options_string, dag_alias, values)
        else:
            status = blast_idl_build(data, args, options_string, dag_alias, values)
    return status

def idl_build(data, args, options_string, dag_alias, values):
    dag_delivery_alias, dag_action, dag_input_path, unused4, unused5, dag_should_gen_sln, dag_sln, dag_options, dag_lang = values
    scons_exe = ''
    if(data.local['is_linux'] == True):
        scons_exe = data.local['output_components_dir'] + '/scatools/' + data.local['variants_dir_name']
    else: #Windows
        scons_exe = data.local['output_components_dir'] + '/scatools/' + data.local['variants_dir_name'] + '.cmd'
    root_path = data.local['input_tree'] + '/' + dag_input_path
    os.chdir(root_path+"")
    command = scons_exe + ' -u idl'
    print('command: ' + command)
    for key, value in os.environ.items():
        print(key, value)
    status = _call_command(data, command)
    return status

def scons_build_tetmesh(data, args, options_string, dag_alias, values):
    status = 0
    os.environ['EXTERNAL_COMPONENT_CACHE_ROOT'] = os.path.abspath(data.machine['component_cache_root'])
    dag_delivery_alias, dag_action, dag_input_path, unused4, unused5, dag_should_gen_sln, dag_sln, dag_options, dag_lang = values
    root_path = data.local['input_tree'] + '/' + dag_input_path
    os.chdir(root_path+"")
    command = 'build -b debug -t mesher'
    if data.options['build_variant'] == data.local['release_name']:
       command = 'build -b release -t mesher'
    elif data.options['build_variant'] == data.local['vtune_name']:
       command = 'build -b vtune -t mesher'
    status = _call_command(data,command)
    return status

def scons_build_tetmesh_test(data, args, options_string, dag_alias, values):
    status = 0
    os.environ['EXTERNAL_COMPONENT_CACHE_ROOT'] = os.path.abspath(data.machine['component_cache_root'])
    dag_delivery_alias, dag_action, dag_input_path, unused4, unused5, dag_should_gen_sln, dag_sln, dag_options, dag_lang = values
    root_path = data.local['input_tree'] + '/' + dag_input_path
    os.chdir(root_path+"")
    command = 'build -b debug -t test'
    if data.options['build_variant'] == data.local['release_name']:
       command = 'build -b release -t test'
    elif data.options['build_variant'] == data.local['vtune_name']:
       command = 'build -b vtune -t test'
    status = _call_command(data,command)
    return status


def scons_build(data, args, options_string, dag_alias, values):
    dag_delivery_alias, dag_action, dag_input_path, unused4, unused5, dag_should_gen_sln, dag_sln, dag_options, dag_lang = values
    
    if dag_alias == 'tetmesh':
        status = scons_build_tetmesh(data, args, options_string, dag_alias, values)
        return status
    if dag_alias == 'tetmesh_test':
        status = scons_build_tetmesh_test(data, args, options_string, dag_alias, values)
        return status
        
    scons_exe = ''
    if(data.local['is_linux'] == True):
        scons_exe = data.local['output_components_dir'] + '/scatools/' + data.local['variants_dir_name']
    else: #Windows
        scons_exe = data.local['output_components_dir'] + '/scatools/' + data.local['variants_dir_name'] + '.cmd'
    root_path = data.local['input_tree'] + '/' + dag_input_path
    os.chdir(root_path+"")
    data = _compute_scons_build_options(data)
    dag_options = dag_options.replace(' UNITYBUILD', '') # Remove Blast only build option.
    command = scons_exe + ' ' + data.local['scons_build_options'] + ' CLEAROLDIDL=' + dag_lang + ' ' + dag_options + ' ' + options_string
    maxAttempts = int(data.options['num_retries'])
    attempt = 1
    msg = 'try: '
    uiPluginBuild = False
    if dag_lang == 'C#' and dag_alias.endswith( "plugin_ui" ):
        # except for special NOIDLAPPEND flagged case,
        if 'NOIDLAPPEND' not in dag_options:
            # unfortunately for UI Plugin build step, the normal SCons build
            # regenerates the SCA IDL type xml without the (named) library tag.
            # So here we detect the UI plugin build and regen the named DLL
            uiPluginBuild = True
    orig_command = command
    while attempt <= maxAttempts:
        command = orig_command

        if 'IDLTYPESAPPEND' in dag_options or uiPluginBuild:
            if uiPluginBuild:
                # UI plugin build step need to re-genrate the named idltypes
                # that were generated during the plugin build step
                msg = 'UI Plugin IDLTYPESAPPEND regen try: '
                idltypes_dag = dag_alias
                # we need to re-gen the regular plugin dag name
                # by removing 'ui' from beginning of dag name
                idltypes_dag = dag_alias.replace( "_ui", "", 1 )
                # hack for plugin dag names not matching ui plugin name
                if idltypes_dag == 'geometry_plugin':
                    idltypes_dag = 'geom_plugin'
                if idltypes_dag == 'midsurface_plugin':
                    idltypes_dag = 'midsurf_plugin'
                idlappendStr = 'CLEAROLDIDL=C# IDLTypesDotNet IDLTYPESAPPEND='+idltypes_dag
                command = command.replace('CLEAROLDIDL=C#', idlappendStr)
            elif 'IDLTYPESAPPEND' in dag_options:
                # The IDLTYPESAPPEND flag will trigger generation
                # of named idltypes DLL and types xml

                named_idltypes = data.local[dag_alias + '_runtime'] + "/Win8664/lib/IDLTypesDotNet"+dag_alias + ".dll"
                print('NAMED_IDLTYPES = ',named_idltypes)
                # incremental build issue.
                # Need to delete named IDLTypes file before building
                # Else get 'type/var already defined errors
                if ( os.path.exists(named_idltypes) ) :
                    print('REMOVING NAMED_IDLTYPES = ',named_idltypes)
                    os.remove(named_idltypes)
                    # file system latency bandaid
                    time.sleep( 1 )

                msg = 'IDLTYPESAPPEND try: '
                idlappendStr = 'IDLTYPESAPPEND=' + dag_alias
                command = command.replace('IDLTYPESAPPEND', idlappendStr)
                command = command + ' scons_all_defaults IDLTypesDotNet'

        if(data.local['is_linux'] == True):
            command = command.replace('IDLTypesDotNet', '')

        # Main (or second) build step
        print(msg + str(attempt) + '\ncommand: ' + command)
        status = _call_command(data, command)
        if status == 0: break
        if attempt >= maxAttempts:
            return status
        attempt += 1
    return status

def downloadModZip(parser, args, subargs, data, suffix = None):
    buildType = data.options['build_variant']
    if vars(args)['mod_variant'] is not None:
        buildType = vars(args)['mod_variant']

    platform = data.local['platform']
    
    # Locate the BOD file and determine the git_commit_id
    git_commit_id = vars(args)['commit']
    git_build_id = vars(args)['build']
    is_bod_found = False
    if git_commit_id is None and git_build_id is None:
        command = 'git describe --match "BOD_Certified-*" --abbrev=0 --tags'
        output = subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout.decode("utf-8")
        git_commit_id = output.strip("BOD_Certified-").strip()[0:8]
        _print_verbosity1("Using GIT commit ID of '" + git_commit_id + "'")
    git_commit_id = git_commit_id[0:8]
    
    if git_build_id is None:
        command = 'git tag -l "BuildID-*-' + git_commit_id + '"'
        output = subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout.decode("utf-8")
        git_build_id = output.strip("BuildID-").strip()[0:6]
        _print_verbosity1("Using GIT build ID of '" + git_build_id + "'")
  
    git_build_commit_id = git_build_id + "-" + git_commit_id
    _print_verbosity1("Using GIT build-commit ID of '" + git_build_commit_id + "'")
    
    # Determine the filename of the zip
    premod_label = git_build_commit_id
    if buildType == data.local['release_name']:
      zipname = premod_label + '-release' #TODO: Can't change these unless the CI scripts are changed.
    if buildType == data.local['debug_name']:
      zipname = premod_label + '-debug' #TODO: Can't change these unless the CI scripts are changed.
    if buildType == data.local['vtune_name']:
      zipname = premod_label + '-vtune' #TODO: Can't change these unless the CI scripts are changed.
    if suffix is not None:
      zipname = zipname + suffix
    if data.local['is_linux'] == True:
      zipname = zipname + '-linux'
    if vars(args)['brokenbuild']:
      zipname = zipname + '-broken'
    zipname = zipname + '.7z'

    # Prepare the output file location
    premod_l_zip = os.path.join(data.local['output_tree'] , zipname)
    if (vars(args)['uselocal'] == False):
        if(os.path.exists(premod_l_zip)):
            os.remove(premod_l_zip)

    # Determine the source file location
    isFound = False
    for artifact_rep in data.artifact:
        file_path = os.path.join(apex_info.get_branch(), git_build_commit_id, zipname)
        storage_info = artifact_rep[platform]['Apex_Mod']
        if(storage.exists(data, storage_info, file_path)):
            isFound = True
            break

    print(premod_l_zip)
    if not (os.path.exists(premod_l_zip)):
        if not isFound:
            print("The following file '" + zipname + "' is not available on the network.")
            print(".")
            print("If this is a broken mod, you can pass -k to the prebuilt command to accept it.")
            print(".")
            print("Visit the network location to determine a suitable build type and/or CL#.")
            return (1, premod_l_zip, premod_label, git_build_commit_id)

        print('Downloading ' + zipname + ' to ' + data.local['output_tree'])
        storage.copy(data, storage_info, file_path, premod_l_zip)

    return (0, premod_l_zip, premod_label, git_build_commit_id)

def _clean_variant(parser, args, subargs, data):
    if vars(args)['force'] != True:
        print("##############################################################################")
        print("#                Are you sure you want to perform a clean?                   #")
        print("#                                                                            #")
        print("# It should never be necessary to perform a 'clean' in order to              #")
        print("# achieve a correct build.  If this is not the case, then there is a bug in  #")
        print("# the build system.  This bug should be investigated and fixed.  Please      #")
        print("# contact the build team, and save any state information necessary for a     #")
        print("# thorough investigation.                                                    #")
        print("#                                                                            #")
        print("# If you still want to clean the output directory, for the current build     #")
        print("# type variant, re-run this command with the force option enabled.           #")
        print("# For example, 'sand clean -f'.                                              #")
        print("##############################################################################")
        return

    variant_dir = _get_variant_dir(data)
    _print_verbosity1('Removing build output directory: ' + variant_dir)
    if os.path.isdir(variant_dir):
        delivery_dir = {'clef' : data.local['clef_dir'], 'glef' : data.local['glef_dir'], 'apex' : data.local['apex_dir']}
        for delivery, root in delivery_dir.items():
            comp_dir = os.path.join(root, 'Components')
            comp_links = glob.glob(os.path.join(comp_dir, '*'))
            # This removes the links in their new location
            for comp_link in comp_links:
                the_component_cache.remove_component_link(os.path.basename(comp_link), os.path.dirname(comp_link))
            # This removes the link if present in the old location
            the_component_cache.remove_component_link(os.path.basename(comp_dir), os.path.dirname(comp_dir))

        contents = glob.glob(os.path.join(variant_dir, '*'))
        for item in contents:
            if os.path.isdir(item):
                if os.path.basename(item) == 'ide':
                    continue
                if os.path.basename(item) == 'reports' and vars(args).get('reports') == False:
                    continue
                if os.path.basename(item).lower().endswith('lock server') and vars(args).get('lockserver') == False:
                    continue
                utilities.rmtree(item)
            else:
                try:
                    os.remove(item)
                except OSError:
                    pass

    if vars(args).get('all') == True:
        # usage: git clean [-d] [-f] [-i] [-n] [-q] [-e <pattern>] [-x | -X] [--] <paths>...
        #
        #     -q, --quiet           do not print names of files removed
        #     -n, --dry-run         dry run
        #     -f, --force           force
        #     -i, --interactive     interactive cleaning
        #     -d                    remove whole directories
        #     -e, --exclude <pattern>
        #                           add <pattern> to ignore rules
        #     -x                    remove ignored files, too
        #     -X                    remove only ignored files
        command = 'git clean -qdfx'
        _call_command(data, command)
    return

def get_build_solutions(data):
    help = ""
    dag_roots = get_compilation_roots(data)
    for dag_alias, values in list(dag_roots.items()):
        help += dag_alias + ', '
    return help

def checkSolutionsValidBuild(args, data):
    dag_roots = get_compilation_roots(data)
    solution_aliases = []
    for dag_alias, values in list(dag_roots.items()):
        solution_aliases.append(dag_alias)
    return checkSolutionsValidImpl(args, data, solution_aliases)

def checkSolutionsValidIDE(args, data):
    solution_aliases = []
    dag_roots = get_compilation_roots(data)
    dag_roots = append_RelativeProject_roots(dag_roots)
    for dag_alias, values in list(dag_roots.items()):
        solution_aliases.append(dag_alias)
    return checkSolutionsValidImpl(args, data, solution_aliases)
