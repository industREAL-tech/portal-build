extends Control
# The direct-to-screen proof scene: a generated application's layout, drawn the same with and
# without BENCH_DIRECT=1 (the root viewport rendered straight to the window, ../patches/0004).
# PROOF_CASE: view (res://theme/ir_view3d.gd -- the generator's IrView3D, copied in by run.sh --
# in the right half of an operator screen), full (3D across the screen with a HUD over it), fog
# (as view, with fog on, so the scene shader keeps its epilogue). Every case also draws text and a
# translucent bar over the 3D and a clipping control (scissor). No depth pre-pass, as the
# generator's 60 fps modes.

# PROOF_MSAA=2|4|8 turns 3D MSAA on (../patches/0005), after direct-to-screen as a generated
# application does (the platform's autoload goes first), or before it with PROOF_MSAA_FIRST=1.
func _ready() -> void:
	var direct := OS.get_environment("BENCH_DIRECT").strip_edges() == "1"
	var msaa: int = {"2": Viewport.MSAA_2X, "4": Viewport.MSAA_4X, "8": Viewport.MSAA_8X}.get(
			OS.get_environment("PROOF_MSAA").strip_edges(), Viewport.MSAA_DISABLED)
	var msaa_first := OS.get_environment("PROOF_MSAA_FIRST").strip_edges() == "1"
	if msaa_first:
		get_viewport().msaa_3d = msaa
	if direct:
		RenderingServer.viewport_set_render_direct_to_screen(get_viewport().get_viewport_rid(), true)
	if not msaa_first:
		get_viewport().msaa_3d = msaa
	var case := OS.get_environment("PROOF_CASE").strip_edges()
	if case == "":
		case = "view"
	print("dts-proof: case=%s direct=%d msaa=%d first=%d" % [case, int(direct), msaa, int(msaa_first)])

	var world := Node3D.new()
	world.name = "World"
	add_child(world)
	var env := Environment.new()
	env.background_mode = Environment.BG_CLEAR_COLOR
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("#404850")
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	env.fog_enabled = case == "fog"
	env.fog_light_color = Color("#8090a0")
	env.fog_density = 0.04
	var we := WorldEnvironment.new()
	we.environment = env
	world.add_child(we)
	RenderingServer.set_default_clear_color(Color("#1d1b1a"))

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 35, 0)
	world.add_child(sun)
	var cam := Camera3D.new()
	cam.position = Vector3(0, 2.2, 6.0)
	cam.look_at_from_position(cam.position, Vector3(0, 0.4, 0))
	world.add_child(cam)

	# floor: unshaded vertex colours (the baked-light path the generator uses)
	var floor_mesh := PlaneMesh.new()
	floor_mesh.size = Vector2(8, 8)
	var fm := StandardMaterial3D.new()
	fm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	fm.albedo_color = Color("#3a332f")
	floor_mesh.material = fm
	var fl := MeshInstance3D.new()
	fl.mesh = floor_mesh
	world.add_child(fl)
	# unshaded gradient-ish boxes, a lit sphere, a transparent quad
	var cols := [Color("#e8541e"), Color("#2fa3d6"), Color("#7ac143"), Color("#f2c200")]
	for i in 4:
		var b := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = Vector3(0.7, 0.7 + i * 0.3, 0.7)
		var m := StandardMaterial3D.new()
		m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		m.albedo_color = cols[i]
		bm.material = m
		b.mesh = bm
		b.position = Vector3(-2.4 + i * 1.6, bm.size.y / 2.0, -0.8)
		b.rotation_degrees = Vector3(0, 20 * i, 0)
		world.add_child(b)
	var s := MeshInstance3D.new()
	var sm := SphereMesh.new()
	var lit := StandardMaterial3D.new()
	lit.albedo_color = Color("#c8c0b8")
	lit.roughness = 0.4
	sm.material = lit
	s.mesh = sm
	s.position = Vector3(0.6, 0.5, 1.2)
	world.add_child(s)
	var q := MeshInstance3D.new()
	var qm := QuadMesh.new()
	qm.size = Vector2(1.6, 1.0)
	var tm := StandardMaterial3D.new()
	tm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	tm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	tm.albedo_color = Color(0.2, 0.9, 1.0, 0.45)
	qm.material = tm
	q.mesh = qm
	q.position = Vector3(-1.2, 0.9, 1.4)
	world.add_child(q)
	# a MultiMesh row of posts
	var mmi := MultiMeshInstance3D.new()
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	var post := CylinderMesh.new()
	post.top_radius = 0.08
	post.bottom_radius = 0.08
	post.height = 1.0
	var pmat := StandardMaterial3D.new()
	pmat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	pmat.albedo_color = Color("#d6dbe4")
	post.material = pmat
	mm.mesh = post
	mm.instance_count = 9
	for i in 9:
		mm.set_instance_transform(i, Transform3D(Basis(), Vector3(-3.2 + i * 0.8, 0.5, -2.6)))
	mmi.multimesh = mm
	world.add_child(mmi)

	# 2D: an operator layout around / over the 3D
	var fill := StyleBoxFlat.new()
	fill.bg_color = Color("#2a2522")
	fill.border_color = Color("#e8541e")
	fill.set_border_width_all(2)
	fill.set_corner_radius_all(6)
	var frame := StyleBoxFlat.new()
	frame.draw_center = false
	frame.border_color = Color("#6b625b")
	frame.set_border_width_all(2)
	if case == "full":
		var hud := PanelContainer.new()
		hud.add_theme_stylebox_override("panel", fill)
		hud.position = Vector2(24, 24)
		hud.size = Vector2(360, 120)
		add_child(hud)
		var l := Label.new()
		l.text = "SPEED 1240 rpm\nTEMP 41.5 C\nSTATE RUNNING"
		hud.add_child(l)
	else:
		var row := HBoxContainer.new()
		row.set_anchors_preset(Control.PRESET_FULL_RECT)
		row.add_theme_constant_override("separation", 16)
		add_child(row)
		row.position = Vector2(16, 16)
		row.size = Vector2(1248, 768)
		var left := PanelContainer.new()
		left.add_theme_stylebox_override("panel", fill)
		left.custom_minimum_size = Vector2(560, 0)
		row.add_child(left)
		var v := VBoxContainer.new()
		left.add_child(v)
		for t in ["Line 3 / Press 2", "Cycle 18.4 s", "Parts 1 204", "Alarms 0"]:
			var l := Label.new()
			l.text = t
			l.add_theme_font_size_override("font_size", 28)
			v.add_child(l)
		var surf := PanelContainer.new()
		surf.add_theme_stylebox_override("panel", frame)
		surf.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(surf)
		var view := Control.new()
		view.set_script(load("res://theme/ir_view3d.gd"))
		view.set("fov", 38.0)
		surf.add_child(view)
	# text and a translucent bar drawn over the 3D picture
	var over := Label.new()
	over.text = "OVER 3D  0.42 mm"
	over.add_theme_font_size_override("font_size", 32)
	over.position = Vector2(820, 700)
	add_child(over)
	var bar := ColorRect.new()
	bar.color = Color(0.9, 0.3, 0.1, 0.35)
	bar.position = Vector2(700, 600)
	bar.size = Vector2(500, 60)
	add_child(bar)
	# a clipping control (scissor): its label runs past the clip on every side
	var clip := Control.new()
	clip.clip_contents = true
	clip.position = Vector2(40, 560)
	clip.size = Vector2(300, 90)
	add_child(clip)
	var cb := ColorRect.new()
	cb.color = Color("#2fa3d6")
	cb.position = Vector2(-20, -20)
	cb.size = Vector2(400, 200)
	clip.add_child(cb)
	var cl := Label.new()
	cl.text = "CLIPPED TEXT RUNS PAST THE EDGE"
	cl.add_theme_font_size_override("font_size", 44)
	cl.position = Vector2(-30, 40)
	clip.add_child(cl)
