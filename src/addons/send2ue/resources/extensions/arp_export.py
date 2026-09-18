import json
import os

import bpy
from send2ue.core.extension import ExtensionBase
from send2ue.core import utilities
from send2ue.constants import ToolInfo, BlenderTypes

PROFILE_PATH = os.path.join(ToolInfo.RESOURCE_FOLDER.value, 'arp', 'unreal_humanoid_anim.json')
ARP_EXPORT_OPERATOR = 'arp_export_fbx_panel'  # bpy.ops.arp.arp_export_fbx_panel
ARP_RIG_MARKER_BONE = 'c_traj'
ARP_UPDATED_KEY = 'arp_updated_4.0'

# Whatever the profile says, a send is one action, one file, rig only, no dummy mesh.
FORCED_SETTINGS = {
    'arp_bake_anim': True,
    'arp_bake_only_active': True,
    'arp_export_separate_fbx': False,
    'arp_ge_sel_only': True,
    'arp_ge_add_dummy_mesh': False,
}


def is_arp_installed():
    """True when Auto-Rig Pro's FBX export operator is registered (bpy.ops.arp lists it only then)."""
    return ARP_EXPORT_OPERATOR in dir(bpy.ops.arp)


def is_arp_rig(scene_object):
    """Same rule Auto-Rig Pro uses: an armature with a c_traj bone."""
    return (
        scene_object is not None
        and scene_object.type == BlenderTypes.SKELETON
        and ARP_RIG_MARKER_BONE in scene_object.data.bones
    )


def load_profile(path=PROFILE_PATH):
    with open(path, 'r', encoding='utf-8') as profile_file:
        return json.load(profile_file)


def apply_profile(scene, profile):
    """
    Sets every profile key on the scene, then the forced settings on top.

    :param bpy.types.Scene scene: The scene whose arp_* properties are set.
    :param dict profile: Auto-Rig Pro scene property names to values.
    :return list: Keys this Auto-Rig Pro version does not have (skipped).
    """
    skipped = []
    for key, value in {**profile, **FORCED_SETTINGS}.items():
        try:
            setattr(scene, key, value)
        except (AttributeError, TypeError):
            skipped.append(key)
    return skipped


def prefixed_file_path(file_path, prefix):
    folder, file_name = os.path.split(file_path)
    if not prefix or file_name.startswith(prefix):
        return file_path
    return os.path.join(folder, prefix + file_name)


def prefixed_asset_path(asset_path, prefix):
    folder, asset_name = asset_path.rsplit('/', 1)
    if not prefix or asset_name.startswith(prefix):
        return asset_path
    return f'{folder}/{prefix}{asset_name}'


class ArpExportExtension(ExtensionBase):
    name = 'arp_export'

    use_arp_export: bpy.props.BoolProperty(
        name='Use Auto-Rig Pro exporter',
        default=False,
        description='Export Auto-Rig Pro rigs with the ARP exporter instead of the stock FBX exporter',
    )
    animation_prefix: bpy.props.StringProperty(
        name='Animation Prefix',
        default='AS_',
        description='Prefix added to the exported file name, and so to the Unreal asset name',
    )
    custom_export_script: bpy.props.StringProperty(
        name='Custom Export Script',
        default='',
        subtype='FILE_PATH',
        description='Optional Auto-Rig Pro custom export script; empty means none',
    )

    def draw_export(self, dialog, layout, properties):
        box = layout.box()
        box.label(text='Auto-Rig Pro export:')
        dialog.draw_property(self, box, 'use_arp_export')
        dialog.draw_property(self, box, 'animation_prefix')
        dialog.draw_property(self, box, 'custom_export_script')

    def pre_validations(self, properties):
        if not self.use_arp_export:
            return True
        rigs = [rig for rig in utilities.get_from_collection(BlenderTypes.SKELETON) if is_arp_rig(rig)]
        if not rigs:
            return True
        if not is_arp_installed():
            utilities.report_error(
                'Auto-Rig Pro is not installed or not enabled in this Blender, '
                'but "Use Auto-Rig Pro exporter" is on.'
            )
            return False
        if bpy.app.version >= (4, 0, 0):
            not_updated = [rig.name for rig in rigs if ARP_UPDATED_KEY not in rig.data.keys()]
            if not_updated:
                utilities.report_error(
                    'These Auto-Rig Pro rigs must be updated for Blender 4 (Auto-Rig Pro menu) '
                    f'before exporting: {", ".join(not_updated)}'
                )
                return False
        # The core needs the skeleton path to build the animation asset data, in every path mode.
        if not properties.unreal_skeleton_asset_path:
            utilities.report_error(
                'Set the Skeleton Asset path under the Paths tab: the Auto-Rig Pro route '
                'imports animation only, onto an existing skeleton.'
            )
            return False
        if properties.import_meshes:
            utilities.report_error(
                'Turn off Meshes under the Import tab: the Auto-Rig Pro route only handles animation.'
            )
            return False
        if self.custom_export_script and not os.path.isfile(bpy.path.abspath(self.custom_export_script)):
            utilities.report_error(f'Custom export script not found: {self.custom_export_script}')
            return False
        return True

    def pre_animation_export(self, asset_data, properties):
        if not self.use_arp_export:
            return
        rig = bpy.data.objects.get(asset_data.get('_armature_object_name', ''))
        if not is_arp_rig(rig):
            return
        scene = bpy.context.scene

        # The FBX file name becomes the Unreal asset name, so the prefix goes on the file.
        asset_data['file_path'] = prefixed_file_path(asset_data['file_path'], self.animation_prefix)
        asset_data['asset_path'] = prefixed_asset_path(asset_data['asset_path'], self.animation_prefix)
        os.makedirs(os.path.dirname(asset_data['file_path']), exist_ok=True)

        skipped = apply_profile(scene, load_profile())
        if skipped:
            print(f'[arp_export] settings unknown to this Auto-Rig Pro version were skipped: {skipped}')
        scene.arp_custom_export_script = (
            bpy.path.abspath(self.custom_export_script) if self.custom_export_script else ''
        )

        # Only Active Action exports rig.animation_data.action; every NLA track is muted at this point.
        action = bpy.data.actions.get(asset_data['_action_name'])
        if action is None:
            utilities.report_error(f'Action "{asset_data["_action_name"]}" no longer exists.')
            return
        if rig.animation_data is None:
            rig.animation_data_create()
        rig.animation_data.action = action

        utilities.deselect_all_objects()
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # ARP reports most errors and still returns FINISHED, so the file on disk is the real check.
        if os.path.exists(asset_data['file_path']):
            os.remove(asset_data['file_path'])
        result = bpy.ops.arp.arp_export_fbx_panel('EXEC_DEFAULT', filepath=asset_data['file_path'])
        if result != {'FINISHED'} or not os.path.isfile(asset_data['file_path']):
            utilities.report_error(
                f'Auto-Rig Pro did not write "{asset_data["file_path"]}" (operator result {result}). '
                'See the system console for the Auto-Rig Pro message.'
            )
            return

        # Tell the stock exporter to leave this file alone; the import step still runs (post hook clears it).
        asset_data['skip'] = True
        asset_data['_arp_export'] = True

    def post_animation_export(self, asset_data, properties):
        if not asset_data.get('_arp_export'):
            return
        asset_data['skip'] = False
        rig = bpy.data.objects.get(asset_data.get('_armature_object_name', ''))
        action = bpy.data.actions.get(asset_data.get('_action_name', ''))
        if rig is not None and rig.animation_data is not None and action is not None:
            rig.animation_data.action = action
