"""
Headless checks for the arp_export extension. Run them with Blender, never with a plain Python.

Helper and validation checks (no Auto-Rig Pro needed):
  blender.exe -b --factory-startup --python scripts/check_arp_export.py

Full export check on a file (Auto-Rig Pro must be enabled in the user profile, so no --factory-startup):
  blender.exe -b path/to/file.blend --python scripts/check_arp_export.py -- --export ActionName

The full check runs the real send in Send to Disk mode by draining the addon's job queue, then reads the
FBX back and checks the clean-skeleton convention (armature node named root, no root bone, pelvis and the
IK roots as top-level bones). The .blend is never saved.
"""
import importlib
import os
import queue
import sys
import tempfile
import traceback
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src', 'addons'))
EXTENSION_FILE = os.path.join(ROOT, 'src', 'addons', 'send2ue', 'resources', 'extensions', 'arp_export.py')

FAILED = []


def check(label, condition, detail=''):
    print(('PASS ' if condition else 'FAIL ') + label + (f' | {detail}' if detail else ''))
    if not condition:
        FAILED.append(label)


def load_extension_module():
    spec = spec_from_loader('arp_export_under_test', SourceFileLoader('arp_export_under_test', EXTENSION_FILE))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_armature(name, bone_names):
    armature = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, armature)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    for bone_name in bone_names:
        bone = armature.edit_bones.new(bone_name)
        bone.head = (0, 0, 0)
        bone.tail = (0, 0, 1)
    bpy.ops.object.mode_set(mode='OBJECT')
    return obj


def test_registration():
    group = getattr(bpy.context.scene.send2ue.extensions, 'arp_export', None)
    check('extension property group registered', group is not None)
    if group is None:
        return
    check('use_arp_export defaults to off', group.use_arp_export is False)
    check('animation_prefix defaults to AS_', group.animation_prefix == 'AS_')
    check('custom_export_script defaults to empty', group.custom_export_script == '')


def test_helpers(ext):
    check('prefix added to file name', ext.prefixed_file_path(r'C:\tmp\Spear_Idle.fbx', 'AS_') == r'C:\tmp\AS_Spear_Idle.fbx')
    check('prefix not doubled', ext.prefixed_file_path(r'C:\tmp\AS_Spear_Idle.fbx', 'AS_') == r'C:\tmp\AS_Spear_Idle.fbx')
    check('empty prefix leaves file name', ext.prefixed_file_path(r'C:\tmp\Spear_Idle.fbx', '') == r'C:\tmp\Spear_Idle.fbx')
    check('prefix added to asset path', ext.prefixed_asset_path('/Game/Anims/Spear_Idle', 'AS_') == '/Game/Anims/AS_Spear_Idle')
    check('asset prefix not doubled', ext.prefixed_asset_path('/Game/Anims/AS_Spear_Idle', 'AS_') == '/Game/Anims/AS_Spear_Idle')

    arp_rig = make_armature('arp_like', ['c_traj', 'pelvis'])
    plain_rig = make_armature('plain', ['Grip', 'Trigger'])
    check('c_traj bone marks an ARP rig', ext.is_arp_rig(arp_rig))
    check('plain armature is not an ARP rig', not ext.is_arp_rig(plain_rig))
    check('None is not an ARP rig', not ext.is_arp_rig(None))

    profile = ext.load_profile()
    expected = {
        'arp_engine_type': 'UNREAL', 'arp_export_rig_type': 'HUMANOID', 'arp_units_x100': True,
        'arp_bake_anim': True, 'arp_ue_ik_anim': True, 'arp_ge_master_traj': False,
        'arp_ue_root_motion': False, 'arp_export_rig_name': 'root', 'arp_ge_add_dummy_mesh': False,
    }
    wrong = {key: profile.get(key) for key, value in expected.items() if profile.get(key) != value}
    check('profile carries the clean-skeleton convention', not wrong, str(wrong))
    check('profile has no custom script key', 'arp_custom_export_script' not in profile)

    skipped = ext.apply_profile(bpy.context.scene, {'arp_engine_type': 'UNREAL', 'not_an_arp_key': 1})
    if ext.is_arp_installed():
        check('apply_profile sets known keys and skips unknown ones', skipped == ['not_an_arp_key'], str(skipped))
    else:
        # the forced settings are applied on top of the profile, so without ARP they are skipped as well
        expected_skipped = {'arp_engine_type', 'not_an_arp_key'} | set(ext.FORCED_SETTINGS)
        check('apply_profile skips everything without ARP', set(skipped) == expected_skipped, str(skipped))

    # leave the file as it was for the export test
    for obj in (arp_rig, plain_rig):
        armature = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.armatures.remove(armature)


def test_validation_without_arp(ext):
    """With the extension on, an ARP rig in Export, and no ARP installed, validation must stop the send."""
    if ext.is_arp_installed():
        print('SKIP validation-without-ARP test (ARP is installed in this profile)')
        return
    group = bpy.context.scene.send2ue.extensions.arp_export
    rig = make_armature('arp_like', ['c_traj', 'pelvis'])
    bpy.data.collections['Export'].objects.link(rig)
    group.use_arp_export = True
    try:
        group.pre_validations(bpy.context.scene.send2ue)
        check('pre_validations raises when ARP is missing', False)
    except RuntimeError as error:
        check('pre_validations raises when ARP is missing', 'Auto-Rig Pro' in str(error), str(error))
    finally:
        group.use_arp_export = False
        armature = rig.data
        bpy.data.objects.remove(rig, do_unlink=True)
        bpy.data.armatures.remove(armature)


def test_export(ext, action_name):
    """Runs the real send in Send to Disk mode by draining the addon's job queue, then inspects the FBX."""
    from send2ue.core import export
    from send2ue.constants import ToolInfo
    properties = bpy.context.scene.send2ue
    rigs = [obj for obj in bpy.data.objects if ext.is_arp_rig(obj)]
    check('one ARP rig in the file', len(rigs) == 1, str([rig.name for rig in rigs]))
    check('ARP installed for the export test', ext.is_arp_installed())
    if len(rigs) != 1 or not ext.is_arp_installed():
        return
    rig = rigs[0]
    export_collection = bpy.data.collections['Export']
    if rig.name not in export_collection.objects:
        export_collection.objects.link(rig)
    action = bpy.data.actions.get(action_name)
    check(f'action {action_name} exists', action is not None)
    if action is None:
        return
    if rig.animation_data is None:
        rig.animation_data_create()
    rig.animation_data.action = action

    out_dir = os.path.join(tempfile.gettempdir(), 'arp_export_check')
    os.makedirs(out_dir, exist_ok=True)
    # no editor in this test: switch off the live path validation before touching path properties
    bpy.context.window_manager.send2ue.path_validation = False
    properties.path_mode = 'send_to_disk'
    properties.disk_animation_folder_path = out_dir
    # the core builds the skeleton path into every animation asset, disk mode included; item assignment
    # stores the value without firing the update callback that would ask the (absent) editor about it
    properties['unreal_skeleton_asset_path'] = '/Game/Check/SK_Check_Skeleton'
    properties.import_meshes = False
    properties.import_animations = True
    properties.auto_stash_active_action = True
    properties.export_all_actions = False
    properties.validate_scene_scale = False
    properties.validate_armature_transforms = False
    properties.validate_unreal_plugins = False
    properties.validate_project_settings = False
    properties.extensions.arp_export.use_arp_export = True

    bpy.app.driver_namespace[ToolInfo.EXECUTION_QUEUE.value] = queue.Queue()
    jobs = bpy.app.driver_namespace[ToolInfo.EXECUTION_QUEUE.value]
    bpy.context.window_manager.send2ue.asset_id = ''
    bpy.context.window_manager.send2ue.asset_data.clear()
    export.send2ue(properties)
    while not jobs.empty():
        function, args, kwargs, message, asset_id, attribute = jobs.get()
        bpy.context.window_manager.send2ue.asset_id = asset_id
        function(*args, **kwargs)

    expected = os.path.join(out_dir, f'AS_{action_name}.fbx')
    check('FBX written with the AS_ prefix', os.path.isfile(expected), expected)
    asset_data = list(bpy.context.window_manager.send2ue.asset_data.values())
    check('exactly one asset was sent', len(asset_data) == 1, str(len(asset_data)))
    if asset_data:
        check('asset_path carries the prefix', asset_data[0]['asset_path'].rsplit('/', 1)[-1] == f'AS_{action_name}')
        check('skip is cleared for the import step', asset_data[0]['skip'] is False)
    check('active action restored on the rig', rig.animation_data.action == action)
    if not os.path.isfile(expected):
        return

    # Read the FBX back in an empty scene and check the clean-skeleton convention.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=expected, ignore_leaf_bones=True)
    armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
    check('one armature in the FBX', len(armatures) == 1)
    if armatures:
        bones = armatures[0].data.bones
        top = sorted(bone.name for bone in bones if bone.parent is None)
        check('armature node is named root', armatures[0].name == 'root', armatures[0].name)
        check('no internal root bone', 'root' not in bones)
        check('pelvis and IK roots are top-level', top == ['ik_foot_root', 'ik_hand_root', 'pelvis'], str(top))
        check('one action in the FBX', len(bpy.data.actions) == 1, str([action.name for action in bpy.data.actions]))


def main():
    send2ue = importlib.import_module('send2ue')
    send2ue.register()
    from send2ue.core import utilities
    utilities.create_collections()
    ext = load_extension_module()

    test_registration()
    test_helpers(ext)
    test_validation_without_arp(ext)

    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if '--export' in argv:
        test_export(ext, argv[argv.index('--export') + 1])

    print(f'\n{len(FAILED)} failed: {FAILED}' if FAILED else '\nALL CHECKS PASSED')
    if FAILED:
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
