bl_info = {
    "name": "UE-Style Viewport Navigation",
    "author": "mehmetcanozkulekci",
    "version": (1, 2, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport: hold Right Mouse / Sidebar (N) > UE Nav",
    "description": "Unreal Engine style fly navigation: hold RMB to look, WASD to move, Q/E down/up, "
                   "wheel while flying changes speed, G toggles Game View (hide grid, lines, gizmos). "
                   "Sidebar panel for camera speed, mouse settings, "
                   "viewport transform and an optional UE mouse mapping (Alt+LMB orbit, Alt+RMB dolly, "
                   "MMB pan, F focus).",
    "category": "3D View",
}

import math

import bpy
from mathutils import Euler, Quaternion, Vector

DRAG_THRESHOLD = 4                                        # px before an RMB press counts as flying
BASE_LOOK = 0.0035                                        # radians per pixel at sensitivity 1.0
SPEED_STEPS = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0]  # m/s for camera speed 1..8 (UE style)

addon_keymaps = []

CONTEXT_MENUS = {
    "OBJECT": "VIEW3D_MT_object_context_menu",
    "EDIT_MESH": "VIEW3D_MT_edit_mesh_context_menu",
    "EDIT_CURVE": "VIEW3D_MT_edit_curve_context_menu",
    "EDIT_ARMATURE": "VIEW3D_MT_armature_context_menu",
    "POSE": "VIEW3D_MT_pose_context_menu",
    "EDIT_GPENCIL": "VIEW3D_MT_gpencil_edit_context_menu",
    "EDIT_LATTICE": "VIEW3D_MT_edit_lattice_context_menu",
    "EDIT_METABALL": "VIEW3D_MT_edit_metaball_context_menu",
    "PARTICLE": "VIEW3D_MT_particle_context_menu",
}

# Mode keymaps are evaluated before "3D View" and bind RMB to their context menu, so the fly
# operator is registered in each of them. Sculpt/paint modes are left alone: RMB there opens
# brush panels and stencil controls.
MODE_KEYMAPS = ("Object Mode", "Mesh", "Curve", "Armature", "Pose", "Lattice", "Metaball", "Particle")


def prefs(context=None):
    return (context or bpy.context).preferences.addons[__name__].preferences


def speed_mps(p):
    return SPEED_STEPS[p.camera_speed - 1] * p.speed_multiplier


# --- viewport transform helpers (the "eye" is what UE shows as the viewport camera position) ----
def find_rv3d(context):
    sd = getattr(context, "space_data", None)
    if sd is not None and sd.type == "VIEW_3D":
        return sd.region_3d
    for area in context.screen.areas if context.screen else ():
        if area.type == "VIEW_3D":
            return area.spaces.active.region_3d
    return None


def eye_of(rv3d):
    return rv3d.view_location + rv3d.view_rotation @ Vector((0.0, 0.0, rv3d.view_distance))


def yaw_pitch_of(rv3d):
    fwd = rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))
    yaw = math.degrees(math.atan2(-fwd.x, fwd.y))          # 0 = looking along +Y, CCW positive
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, fwd.z))))
    return yaw, pitch


def set_view(rv3d, eye=None, yaw=None, pitch=None):
    cur_eye = eye_of(rv3d)
    cy, cp = yaw_pitch_of(rv3d)
    yaw = cy if yaw is None else yaw
    pitch = cp if pitch is None else max(-89.0, min(89.0, pitch))
    rot = Euler((math.radians(90.0 + pitch), 0.0, math.radians(yaw)), "XYZ").to_quaternion()
    eye = cur_eye if eye is None else Vector(eye)
    rv3d.view_rotation = rot
    rv3d.view_location = eye - rot @ Vector((0.0, 0.0, rv3d.view_distance))


def _get_eye(self):
    rv3d = find_rv3d(bpy.context)
    return tuple(eye_of(rv3d)) if rv3d else (0.0, 0.0, 0.0)


def _set_eye(self, value):
    rv3d = find_rv3d(bpy.context)
    if rv3d:
        set_view(rv3d, eye=value)


def _get_yaw(self):
    rv3d = find_rv3d(bpy.context)
    return yaw_pitch_of(rv3d)[0] if rv3d else 0.0


def _set_yaw(self, value):
    rv3d = find_rv3d(bpy.context)
    if rv3d:
        set_view(rv3d, yaw=value)


def _get_pitch(self):
    rv3d = find_rv3d(bpy.context)
    return yaw_pitch_of(rv3d)[1] if rv3d else 0.0


def _set_pitch(self, value):
    rv3d = find_rv3d(bpy.context)
    if rv3d:
        set_view(rv3d, pitch=value)


class UENAV_ViewProps(bpy.types.PropertyGroup):
    location: bpy.props.FloatVectorProperty(name="Location", size=3, subtype="TRANSLATION", unit="LENGTH",
                                            get=_get_eye, set=_set_eye)
    yaw: bpy.props.FloatProperty(name="Yaw", description="0 = looking along +Y, positive turns left",
                                 get=_get_yaw, set=_set_yaw, step=100, precision=1)
    pitch: bpy.props.FloatProperty(name="Pitch", description="Positive looks up", min=-89.0, max=89.0,
                                   get=_get_pitch, set=_set_pitch, step=100, precision=1)


class UENAV_OT_fly(bpy.types.Operator):
    """Hold Right Mouse to fly (UE style); a short click opens the context menu"""
    bl_idname = "view3d.ue_fly"
    bl_label = "UE Fly Navigation"
    bl_options = {"BLOCKING"}

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D" or context.region_data is None:
            return {"PASS_THROUGH"}
        self.rv3d = context.region_data
        self.start = (event.mouse_x, event.mouse_y)
        self.last = self.start
        self.flying = False
        self.keys = set()
        self.boost = 1.0
        self.timer = None
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def begin_flight(self, context):
        rv3d = self.rv3d
        if rv3d.view_perspective in {"CAMERA", "ORTHO"}:
            rv3d.view_perspective = "PERSP"
        rot = rv3d.view_rotation.copy()
        # pivot moves to the eye so rotation happens around the viewer, like a game camera
        self.orig_dist = rv3d.view_distance
        rv3d.view_location = rv3d.view_location + rot @ Vector((0.0, 0.0, rv3d.view_distance))
        rv3d.view_distance = 0.0
        self.timer = context.window_manager.event_timer_add(1 / 60, window=context.window)
        context.window.cursor_modal_set("NONE")
        self.flying = True
        self.update_header(context)

    def end_flight(self, context):
        rv3d = self.rv3d
        if self.timer:
            context.window_manager.event_timer_remove(self.timer)
            self.timer = None
        # restore an orbit pivot in front of the eye so the next orbit feels natural
        d = max(self.orig_dist, 1.0)
        rv3d.view_location = rv3d.view_location - rv3d.view_rotation @ Vector((0.0, 0.0, d))
        rv3d.view_distance = d
        context.window.cursor_modal_restore()
        context.window.cursor_warp(*self.start)
        if context.area:
            context.area.header_text_set(None)
        for a in context.screen.areas:
            if a.type == "VIEW_3D":
                a.tag_redraw()          # refresh the sidebar transform readout

    def look(self, dx, dy):
        p = prefs()
        k = BASE_LOOK * p.mouse_sensitivity
        if p.invert_y:
            dy = -dy
        rv3d = self.rv3d
        rot = rv3d.view_rotation
        yaw = Quaternion((0.0, 0.0, 1.0), -dx * k)
        pitch = Quaternion(rot @ Vector((1.0, 0.0, 0.0)), dy * k)
        new = yaw @ pitch @ rot
        fwd = new @ Vector((0.0, 0.0, -1.0))
        rv3d.view_rotation = new if abs(fwd.z) < 0.995 else yaw @ rot   # never flip over the poles

    def move(self, dt):
        rot = self.rv3d.view_rotation
        fwd = rot @ Vector((0.0, 0.0, -1.0))
        right = rot @ Vector((1.0, 0.0, 0.0))
        up = Vector((0.0, 0.0, 1.0))
        v = Vector((0.0, 0.0, 0.0))
        if "W" in self.keys: v += fwd
        if "S" in self.keys: v -= fwd
        if "D" in self.keys: v += right
        if "A" in self.keys: v -= right
        if "E" in self.keys: v += up
        if "Q" in self.keys: v -= up
        if v.length > 0:
            self.rv3d.view_location += v.normalized() * speed_mps(prefs()) * self.boost * dt

    def update_header(self, context):
        if context.area:
            p = prefs()
            context.area.header_text_set(
                f"UE Fly  |  camera speed {p.camera_speed} ({speed_mps(p):g} m/s, wheel)  |  WASD move, "
                f"Q/E down/up, Shift fast, Ctrl slow  |  release RMB to stop")

    def modal(self, context, event):
        if context.area is None:
            return {"CANCELLED"}
        if event.type == "MOUSEMOVE":
            if not self.flying:
                if abs(event.mouse_x - self.start[0]) + abs(event.mouse_y - self.start[1]) > DRAG_THRESHOLD:
                    self.begin_flight(context)
                    self.last = (event.mouse_x, event.mouse_y)
                return {"RUNNING_MODAL"}
            dx = event.mouse_x - self.last[0]; dy = event.mouse_y - self.last[1]
            if dx or dy:
                self.look(dx, dy)
                context.window.cursor_warp(*self.start)   # parked cursor = unbounded look
                self.last = self.start
            return {"RUNNING_MODAL"}

        if event.type in {"W", "A", "S", "D", "Q", "E"}:
            if not self.flying and event.value == "PRESS":
                self.begin_flight(context)
            if event.value == "PRESS":
                self.keys.add(event.type)
            elif event.value == "RELEASE":
                self.keys.discard(event.type)
            return {"RUNNING_MODAL"}

        if event.type in {"LEFT_SHIFT", "RIGHT_SHIFT", "LEFT_CTRL", "RIGHT_CTRL"}:
            self.boost = 3.0 if event.shift else (0.3 if event.ctrl else 1.0)
            return {"RUNNING_MODAL"}

        if event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            p = prefs()
            p.camera_speed = min(max(p.camera_speed + (1 if event.type == "WHEELUPMOUSE" else -1), 1), 8)
            if self.flying:
                self.update_header(context)
            return {"RUNNING_MODAL"}

        if event.type == "TIMER" and self.flying:
            self.boost = 3.0 if event.shift else (0.3 if event.ctrl else 1.0)
            self.move(1 / 60)
            context.area.tag_redraw()
            return {"RUNNING_MODAL"}

        if (event.type == "RIGHTMOUSE" and event.value == "RELEASE") or event.type == "ESC":
            if self.flying:
                self.end_flight(context)
                context.area.tag_redraw()
            elif event.type == "RIGHTMOUSE":
                try:
                    bpy.ops.wm.call_menu(name=CONTEXT_MENUS.get(context.mode, "VIEW3D_MT_object_context_menu"))
                except RuntimeError:
                    pass
            return {"FINISHED"}

        return {"RUNNING_MODAL"} if self.flying else {"PASS_THROUGH"}


class UENAV_OT_level_view(bpy.types.Operator):
    """Level the view: keep position and yaw, set pitch to 0"""
    bl_idname = "view3d.ue_level_view"
    bl_label = "Level View"

    def execute(self, context):
        rv3d = find_rv3d(context)
        if rv3d:
            if rv3d.view_perspective == "CAMERA":
                rv3d.view_perspective = "PERSP"
            set_view(rv3d, pitch=0.0)
        return {"FINISHED"}


class UENAV_OT_game_view(bpy.types.Operator):
    """Game View (UE): hide/show grid, axes, outlines, light and camera lines and gizmos"""
    bl_idname = "view3d.ue_game_view"
    bl_label = "Toggle Game View"

    @classmethod
    def poll(cls, context):
        return find_rv3d(context) is not None

    def execute(self, context):
        sd = context.space_data if getattr(context.space_data, "type", "") == "VIEW_3D" else None
        if sd is None:
            for a in context.screen.areas:
                if a.type == "VIEW_3D":
                    sd = a.spaces.active
                    break
        game = sd.overlay.show_overlays          # overlays on -> switch to game view
        sd.overlay.show_overlays = not game
        sd.show_gizmo = not game
        self.report({"INFO"}, "Game View on" if game else "Game View off")
        return {"FINISHED"}


def _remap(self, context):
    unregister_keymaps()
    register_keymaps()


class UENAV_Preferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    camera_speed: bpy.props.IntProperty(name="Camera Speed", description="UE style camera speed 1-8",
                                        default=4, min=1, max=8)
    speed_multiplier: bpy.props.FloatProperty(name="Speed Multiplier", default=1.0, min=0.01, soft_max=10.0)
    mouse_sensitivity: bpy.props.FloatProperty(name="Mouse Sensitivity", default=1.0, min=0.1, max=5.0)
    invert_y: bpy.props.BoolProperty(name="Invert Mouse Y", default=False)
    game_view_key: bpy.props.EnumProperty(
        name="Game View Key",
        description="Key that toggles Game View. G replaces Blender's Grab shortcut (use the Move tool instead)",
        items=(("G", "G (UE style, replaces Grab)", ""),
               ("SHIFT_ACCENT", "Shift + `", ""),
               ("NONE", "None (button only)", "")),
        default="G", update=_remap)
    ue_mouse_mapping: bpy.props.BoolProperty(
        name="UE Mouse Mapping",
        description="Alt+LMB orbit, Alt+RMB dolly, MMB pan, F focus (Object Mode). Changes Blender defaults",
        default=True, update=_remap)

    def draw(self, context):
        draw_settings(self.layout, self)


def draw_settings(layout, p):
    col = layout.column(align=True)
    col.prop(p, "camera_speed", slider=True)
    col.prop(p, "speed_multiplier")
    col.label(text=f"= {speed_mps(p):g} m/s", icon="FORWARD")
    col = layout.column(align=True)
    col.prop(p, "mouse_sensitivity", slider=True)
    col.prop(p, "invert_y")
    col.prop(p, "ue_mouse_mapping")
    col.prop(p, "game_view_key")


class UENAV_PT_base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UE Nav"


class UENAV_PT_main(UENAV_PT_base, bpy.types.Panel):
    bl_label = "Camera Speed & Mouse"

    def draw(self, context):
        sd = context.space_data
        game = sd is not None and sd.type == "VIEW_3D" and not sd.overlay.show_overlays
        self.layout.operator("view3d.ue_game_view", text="Game View: ON" if game else "Game View: OFF",
                             icon="HIDE_ON" if game else "HIDE_OFF", depress=game)
        draw_settings(self.layout, prefs(context))


class UENAV_PT_transform(UENAV_PT_base, bpy.types.Panel):
    bl_label = "Viewport Transform"

    def draw(self, context):
        layout = self.layout
        rv3d = find_rv3d(context)
        if rv3d is None:
            layout.label(text="No 3D view")
            return
        vp = context.window_manager.ue_nav_view
        if rv3d.view_perspective == "CAMERA":
            layout.label(text="Looking through the scene camera", icon="CAMERA_DATA")
        col = layout.column(align=True)
        col.prop(vp, "location")
        col = layout.column(align=True)
        col.prop(vp, "yaw")
        col.prop(vp, "pitch")
        layout.prop(context.space_data, "lens", text="Lens (mm)")
        layout.operator("view3d.ue_level_view", icon="AXIS_FRONT")


class UENAV_PT_camera(UENAV_PT_base, bpy.types.Panel):
    bl_label = "Scene Camera"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("view3d.camera_to_view", text="Align Active Camera to View", icon="CAMERA_DATA")
        col.operator("view3d.view_camera", text="Look Through Active Camera", icon="VIEW_CAMERA")
        cam = context.scene.camera
        self.layout.label(text=f"Active: {cam.name if cam else 'none'}")


class UENAV_PT_help(UENAV_PT_base, bpy.types.Panel):
    bl_label = "Shortcuts"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        for keys, what in (("RMB hold + mouse", "look around"),
                           ("RMB + W/A/S/D", "move"),
                           ("RMB + Q / E", "down / up"),
                           ("RMB + wheel", "camera speed"),
                           ("Shift / Ctrl", "fast / slow"),
                           ("RMB click", "context menu"),
                           ("Alt + LMB", "orbit"),
                           ("Alt + RMB", "dolly"),
                           ("MMB", "pan"),
                           ("F", "focus selected"),
                           (GAME_VIEW_LABEL.get(prefs(context).game_view_key, "-"), "game view")):
            row = col.row()
            row.label(text=keys)
            row.label(text=what)
        if not prefs(context).ue_mouse_mapping:
            self.layout.label(text="Alt/MMB/F mapping is off", icon="INFO")


GAME_VIEW_LABEL = {"G": "G", "SHIFT_ACCENT": "Shift + `", "NONE": "button"}
# keymaps where G is Grab: the game-view item must sit in each of them to take precedence
GRAB_KEYMAPS = ("3D View", "Object Mode", "Mesh", "Curve", "Armature", "Pose", "Lattice", "Metaball",
                "Particle", "Sculpt", "Weight Paint", "Vertex Paint", "Image Paint")


def register_keymaps():
    kc = bpy.context.window_manager.keyconfigs.addon
    if not kc:
        return
    km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
    addon_keymaps.append((km, km.keymap_items.new(UENAV_OT_fly.bl_idname, "RIGHTMOUSE", "PRESS")))
    for name in MODE_KEYMAPS:
        kmm = kc.keymaps.new(name=name, space_type="EMPTY")
        addon_keymaps.append((kmm, kmm.keymap_items.new(UENAV_OT_fly.bl_idname, "RIGHTMOUSE", "PRESS")))
    try:
        use_ue = prefs().ue_mouse_mapping
    except KeyError:
        use_ue = True
    try:
        gv = prefs().game_view_key
    except KeyError:
        gv = "G"
    if gv != "NONE":
        for name in GRAB_KEYMAPS:
            kmg = km if name == "3D View" else kc.keymaps.new(name=name, space_type="EMPTY")
            if gv == "G":
                kmi = kmg.keymap_items.new("view3d.ue_game_view", "G", "PRESS")
            else:
                kmi = kmg.keymap_items.new("view3d.ue_game_view", "ACCENT_GRAVE", "PRESS", shift=True)
            addon_keymaps.append((kmg, kmi))
    if use_ue:
        addon_keymaps.append((km, km.keymap_items.new("view3d.rotate", "LEFTMOUSE", "PRESS", alt=True)))
        addon_keymaps.append((km, km.keymap_items.new("view3d.zoom", "RIGHTMOUSE", "PRESS", alt=True)))
        addon_keymaps.append((km, km.keymap_items.new("view3d.move", "MIDDLEMOUSE", "PRESS")))
        kmo = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
        addon_keymaps.append((kmo, kmo.keymap_items.new("view3d.view_selected", "F", "PRESS")))


def unregister_keymaps():
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    addon_keymaps.clear()


classes = (UENAV_ViewProps, UENAV_OT_fly, UENAV_OT_level_view, UENAV_OT_game_view, UENAV_Preferences,
           UENAV_PT_main, UENAV_PT_transform, UENAV_PT_camera, UENAV_PT_help)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.WindowManager.ue_nav_view = bpy.props.PointerProperty(type=UENAV_ViewProps)
    register_keymaps()


def unregister():
    unregister_keymaps()
    del bpy.types.WindowManager.ue_nav_view
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
