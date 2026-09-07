<p align="center">
  <img width="300" src="https://github.com/poly-hammer/BlenderTools/blob/main/docs/images/1.png?raw=true" alt="icon"/>
</p>
<h1 align="center">Blender Tools</h1>

Blender add-ons that move assets from Blender into Unreal Engine, forked to add an Auto-Rig Pro export route to Send to Unreal.

This is a fork of [poly-hammer/BlenderTools](https://github.com/poly-hammer/BlenderTools), the community-maintained continuation of the original [Epic Games repository](https://github.com/EpicGamesExt/BlenderTools). It is not affiliated with Epic Games or with the poly-hammer maintainers. Upstream fixes are pulled from poly-hammer; the Epic repository's code has not changed since 2024.

## What this fork adds

Send to Unreal exports animation with Blender's FBX exporter. Rigs built with [Auto-Rig Pro](https://blendermarket.com/products/auto-rig-pro) need Auto-Rig Pro's own exporter (bone renaming, IK bones, root motion), so a stock send puts the clip on the wrong skeleton. This fork routes those rigs through Auto-Rig Pro automatically, so one click sends the active action onto an existing Unreal skeleton.

Planned for version one (in progress, nothing released yet):

- `arp_export` extension. When a rig in the `Export` collection has Auto-Rig Pro's `c_traj` bone, the animation is exported with `arp.arp_export_fbx_panel` and a bundled Unreal humanoid profile (animated IK bones, root motion, units x100, baked actions, only the active action). Other armatures keep the stock exporter.
- A bundled custom export script that re-parents `ik_hand_root` and `ik_foot_root` under `root` in the export rig, so the FBX hierarchy matches a skeleton that was imported with those bones under root.
- An asset name prefix (`AS_` by default) applied to the exported file, so action names in the .blend stay untouched.

Project-specific values (skeleton path, import folder) belong in a Send to Unreal settings template loaded through the Settings Dialog; none are stored in this repository. Auto-Rig Pro is a paid add-on and is not included.

Everything else is upstream Send to Unreal and UE to Rigify, unchanged. Their documentation lives at [poly-hammer.github.io/BlenderTools](https://poly-hammer.github.io/BlenderTools/).

![Send to Unreal](docs/images/send2ue/4.gif)

## Requirements

- Blender 5.1 is what this fork is tested on; upstream supports 3.6 and later. Send to Unreal is a legacy add-on: install it with Preferences > Add-ons > Install from Disk.
- Unreal Engine 5.8 with the Python Editor Script Plugin enabled and Python Remote Execution turned on in the project settings.
- Auto-Rig Pro, only for the `arp_export` route.

## Install

There are no releases on this fork yet. To build the add-on zip from source, run this in the repository root:

```
python -c "import sys; sys.path.insert(0, 'tests'); from utils.addon_packager import AddonPackager; AddonPackager('send2ue', 'src/addons/send2ue', 'release').zip_addon()"
```

The zip appears in `release/`. Install it from Preferences > Add-ons > Install from Disk and enable **Send to Unreal**. Load your project's settings template in Pipeline > Export > Settings Dialog, turn on the extension in the Export tab, and put the rig in the `Export` collection.

## Layout

- `src/addons/send2ue` and `src/addons/ue2rigify`: the add-ons.
- `src/addons/send2ue/resources/extensions`: bundled extensions, including `arp_export`.
- `src/addons/send2ue/resources/arp`: the Auto-Rig Pro export profile and the custom export script.
- `docs`: upstream documentation source (mkdocs).
- `tests`: upstream test suite and the add-on packager.

## Keeping up with upstream

The `upstream` remote is poly-hammer. Merge `upstream/main` into `main` from time to time. The changes in this fork are additive (one extension and one resources folder), so merges stay small.

## License

MIT, see [LICENSE.md](LICENSE.md). The original code is copyright Epic Games, Inc.; changes in this fork are under the same license.
