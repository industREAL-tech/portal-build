extends Node3D
## epilogue-proof: renders fixed rows of quads under many Environment settings into PNGs,
## so a compare script can report exactly which pixels the colour-epilogue patches change.
## Everything is built in code in _ready(); the manifest records pixel rects and expected
## colours from the same constants used to place the quads.

const PX_W := 512
const PX_H := 384
const W := 16.0      # world units of viewport width  (512 px @ 32 px/unit)
const H := 12.0      # world units of viewport height (384 px @ 32 px/unit)
const PPU := 32.0    # pixels per world unit

# Row bands as [world_y_lo, world_y_hi], stacked to fill [-6, 6].
const ROW_A := [-6.0, -4.0]  # 2 units tall
const ROW_B := [-3.0, -2.0]
const ROW_C := [-1.0, 0.0]
const ROW_D := [1.0, 2.0]
const ROW_E := [3.0, 4.0]
const ROW_F := [5.0, 6.0]

const ROW_B_COLORS: Array = [
	Color8(0, 0, 0), Color8(1, 2, 3), Color8(4, 4, 4), Color8(7, 20, 38),
	Color8(10, 10, 10), Color8(16, 16, 16), Color8(32, 32, 32), Color8(42, 37, 34),
	Color8(64, 64, 64), Color8(96, 64, 32), Color8(128, 128, 128), Color8(160, 200, 240),
	Color8(192, 192, 192), Color8(220, 30, 60), Color8(250, 250, 250), Color8(255, 255, 255),
]

const ROW_D_FIRST: Array = [
	Vector3(-0.5, 0.25, 0.5), Vector3(1.5, 0.5, -2.0),
	Vector3(0.002, 0.01, 0.03), Vector3(0.9, 1.2, 0.1),
]
const ROW_D_FOG_DISABLED: Array = [
	Vector3(0.2, 0.4, 0.6), Vector3(0.03, 0.02, 0.01),
]

const ROW_E_BASE: Array = [
	Color8(255, 0, 0), Color8(0, 255, 0), Color8(0, 0, 255), Color8(128, 128, 128),
]

const ROW_F_COLORS: Array = [
	Color8(200, 100, 50), Color8(50, 200, 100), Color8(100, 50, 200), Color8(128, 128, 128),
]

const TONEMAPPERS: Array = [
	["linear", Environment.TONE_MAPPER_LINEAR],
	["reinhardt", Environment.TONE_MAPPER_REINHARDT],
	["filmic", Environment.TONE_MAPPER_FILMIC],
	["aces", Environment.TONE_MAPPER_ACES],
	["agx", Environment.TONE_MAPPER_AGX],
]
const EXPOSURES: Array = [1.0, 0.5, 2.0]

var _rows: Dictionary = {}

# The light exists in every case so lit rows are deterministic.
var _dir_light: DirectionalLight3D
var _decal: Decal
var _world_env: WorldEnvironment
var _env: Environment


func _ready() -> void:
	if not OS.get_environment("PROOF_BENCH").is_empty():
		_bench()
		return
	var out := OS.get_environment("PROOF_OUT")
	if out.is_empty():
		printerr("PROOF_OUT is required")
		get_tree().quit(2)
		return
	var dir_err := DirAccess.make_dir_recursive_absolute(out)
	if dir_err != OK and dir_err != ERR_ALREADY_EXISTS:
		printerr("cannot create PROOF_OUT %s: %d" % [out, dir_err])
		get_tree().quit(2)
		return

	_make_camera()
	_build_rows()
	_dir_light = _make_directional_light()

	_world_env = WorldEnvironment.new()
	_env = Environment.new()
	_env.background_mode = Environment.BG_COLOR
	_env.background_color = Color8(30, 30, 30)
	_env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_env.ambient_light_color = Color8(60, 60, 60)
	_env.ambient_light_energy = 1.0
	_world_env.environment = _env
	add_child(_world_env)

	var cases := _build_cases()
	# Build the manifest up front (rects + expected colours come from the same constants).
	var manifest := {
		"image_size": [PX_W, PX_H],
		"cases": cases,
		"rows": _rows,
	}

	for i in range(3):
		await get_tree().process_frame

	for case_name in cases:
		# hdr_<case>: the same case on a floating-point (HDR 2D) render target.
		var hdr: bool = case_name.begins_with("hdr_")
		get_viewport().use_hdr_2d = hdr
		# decal_<case>: the same case with a decal over the first four row B quads.
		_decal.visible = case_name.begins_with("decal_")
		var base: String = case_name.trim_prefix("hdr_").trim_prefix("decal_")
		if base == "noenv":
			_world_env.environment = null
		else:
			_world_env.environment = _env
			_apply_case(_env, base)
		await get_tree().process_frame
		await get_tree().process_frame
		await get_tree().process_frame
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		img.convert(Image.FORMAT_RGB8)
		var err := img.save_png(out.path_join("%s.png" % case_name))
		if err != OK:
			printerr("failed to save %s.png: %d" % [case_name, err])
			get_tree().quit(2)
			return
		print("IR proof case %s" % case_name)

	var json := JSON.stringify(manifest, "\t")
	var f := FileAccess.open(out.path_join("manifest.json"), FileAccess.WRITE)
	if f == null:
		printerr("cannot write manifest: %s" % out.path_join("manifest.json"))
		get_tree().quit(2)
		return
	f.store_string(json)
	f.close()

	print("proof: done %d cases" % cases.size())
	get_tree().quit(0)


func _tonemap_enum(name: String) -> int:
	match name:
		"linear":
			return Environment.TONE_MAPPER_LINEAR
		"reinhardt":
			return Environment.TONE_MAPPER_REINHARDT
		"filmic":
			return Environment.TONE_MAPPER_FILMIC
		"aces":
			return Environment.TONE_MAPPER_ACES
		"agx":
			return Environment.TONE_MAPPER_AGX
	return Environment.TONE_MAPPER_LINEAR


func _build_cases() -> Array:
	var cases: Array = ["noenv"]
	for tm in TONEMAPPERS:
		for exp in EXPOSURES:
			for fog in [false, true]:
				for glow in [false, true]:
					cases.append("%s_e%.1f_fog%d_glow%d" % [tm[0], exp, 1 if fog else 0, 1 if glow else 0])
	# The cases where the sRGB round trip is skipped, again on a floating-point render target.
	cases.append_array(["hdr_noenv", "hdr_linear_e1.0_fog0_glow0", "hdr_linear_e1.0_fog1_glow0"])
	# A float target with glow: effects run in post with a luminance multiplier of 1.0.
	cases.append("hdr_linear_e1.0_fog0_glow1")
	# Decals change the albedo in linear space, so the round trip must stay for those quads.
	cases.append_array(["decal_noenv", "decal_linear_e1.0_fog0_glow0"])
	return cases


func _apply_case(env: Environment, case_name: String) -> void:
	var parts := case_name.split("_")
	var tm_name: String = parts[0]
	var exp: float = float(parts[1].trim_prefix("e"))
	var fog: bool = int(parts[2].trim_prefix("fog")) == 1
	var glow: bool = int(parts[3].trim_prefix("glow")) == 1
	env.tonemap_mode = _tonemap_enum(tm_name)
	env.tonemap_exposure = exp
	env.fog_enabled = fog
	env.fog_density = 0.05
	env.fog_light_color = Color8(120, 140, 160)
	env.glow_enabled = glow
	# No glow/bloom settings change: glow presence only toggles the effect off/on.
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color8(30, 30, 30)


func _make_camera() -> void:
	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = 12.0
	cam.position = Vector3(0.0, 0.0, 10.0)
	cam.current = true
	add_child(cam)


func _make_directional_light() -> DirectionalLight3D:
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-30.0, 20.0, 0.0)
	light.shadow_enabled = false
	add_child(light)
	return light


# Convert a world-space rect [cx, cy, w, h] to a pixel rect [x0, y0, x1, y1) top-left origin.
func _rect_px(cx: float, cy: float, w: float, h: float) -> Array:
	var x0 := int(round((cx - w * 0.5 + W * 0.5) * PPU))
	var x1 := int(round((cx + w * 0.5 + W * 0.5) * PPU))
	var y0 := int(round((H * 0.5 - (cy + h * 0.5)) * PPU))
	var y1 := int(round((H * 0.5 - (cy - h * 0.5)) * PPU))
	return [x0, y0, x1, y1]


# Centre x for the i-th of n quads spread evenly across [-8, 8].
func _xpos(i: int, n: int) -> float:
	return -W * 0.5 + (i + 0.5) * (W / n)


func _build_rows() -> void:
	_build_decal()
	_build_row_a()
	_build_row_b()
	_build_row_c()
	_build_row_d()
	_build_row_e()
	_build_row_f()


func _build_row_a() -> void:
	var img := Image.create(256, 2, false, Image.FORMAT_RGB8)
	for i in 256:
		img.set_pixel(i, 0, Color(i / 255.0, i / 255.0, i / 255.0))
		img.set_pixel(i, 1, Color(i / 255.0, (255 - i) / 255.0, ((i * 7) % 256) / 255.0))
	var tex := ImageTexture.create_from_image(img)

	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_texture = tex
	mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST

	var mesh := QuadMesh.new()
	mesh.size = Vector2(16.0, 2.0)
	mesh.material = mat
	var quad := MeshInstance3D.new()
	quad.mesh = mesh
	quad.position = Vector3(0.0, (ROW_A[0] + ROW_A[1]) * 0.5, 0.0)
	add_child(quad)

	# Rects: 256 columns x 2 texel rows, each texel's own 2x32 px region (row A is 512x64 px).
	# Texture row 0 (grey ramp) maps to the upper image band, row 1 (colour ramp) to the lower.
	var regions: Array = []
	for ty in 2:
		for i in 256:
			var x0 := i * 2
			var x1 := x0 + 2
			var y0: int
			var y1: int
			if ty == 0:
				y0 = int((H * 0.5 - ROW_A[1]) * PPU)
				y1 = int((H * 0.5 - (ROW_A[0] + (ROW_A[1] - ROW_A[0]) / 2.0)) * PPU)
			else:
				y0 = int((H * 0.5 - (ROW_A[0] + (ROW_A[1] - ROW_A[0]) / 2.0)) * PPU)
				y1 = int((H * 0.5 - ROW_A[0]) * PPU)
			var c: Color
			if ty == 0:
				c = Color(i / 255.0, i / 255.0, i / 255.0)
			else:
				c = Color(i / 255.0, (255 - i) / 255.0, ((i * 7) % 256) / 255.0)
			regions.append([x0, y0, x1, y1, _col8(c)])
	_rows["A"] = {"quads": [_rect_px(0.0, (ROW_A[0] + ROW_A[1]) * 0.5, 16.0, 2.0)], "regions": regions}


# A decal over row B's first four quads (it projects along its local -Y, turned to face -Z).
func _build_decal() -> void:
	var img := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	img.fill(Color8(200, 40, 40, 255))
	_decal = Decal.new()
	_decal.texture_albedo = ImageTexture.create_from_image(img)
	_decal.albedo_mix = 0.5
	_decal.size = Vector3(4.0, 2.0, 1.0)
	_decal.rotation_degrees = Vector3(90.0, 0.0, 0.0)
	var cy := (ROW_B[0] + ROW_B[1]) * 0.5
	_decal.position = Vector3(-6.0, cy, 0.0)
	_decal.visible = false
	add_child(_decal)
	var r := _rect_px(-6.0, cy, 4.0, 1.0)
	_rows["decal"] = {"quads": [[r[0], r[1], r[2], r[3]]]}


func _build_row_b() -> void:
	var n := ROW_B_COLORS.size()
	var quads: Array = []
	for i in n:
		var cx := _xpos(i, n)
		var cy := (ROW_B[0] + ROW_B[1]) * 0.5
		var mat := StandardMaterial3D.new()
		mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		mat.albedo_color = ROW_B_COLORS[i]
		var mesh := QuadMesh.new()
		mesh.size = Vector2(1.0, 1.0)
		mesh.material = mat
		var quad := MeshInstance3D.new()
		quad.mesh = mesh
		quad.position = Vector3(cx, cy, 0.0)
		add_child(quad)
		var rect := _rect_px(cx, cy, 1.0, 1.0)
		quads.append([rect[0], rect[1], rect[2], rect[3], _col8(ROW_B_COLORS[i])])
	_rows["B"] = {"quads": quads}


func _build_row_c() -> void:
	var n := ROW_B_COLORS.size()
	var quads: Array = []
	for i in n:
		var cx := _xpos(i, n)
		var cy := (ROW_C[0] + ROW_C[1]) * 0.5
		var color: Color = ROW_B_COLORS[i]

		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([
			Vector3(-0.5, 0.5, 0.0), Vector3(-0.5, -0.5, 0.0),
			Vector3(0.5, -0.5, 0.0), Vector3(0.5, 0.5, 0.0),
		])
		arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([
			Vector3(0, 0, 1), Vector3(0, 0, 1), Vector3(0, 0, 1), Vector3(0, 0, 1),
		])
		arrays[Mesh.ARRAY_COLOR] = PackedColorArray([color, color, color, color])
		arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2, 2, 3, 0])

		var mat := StandardMaterial3D.new()
		mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		mat.vertex_color_use_as_albedo = true
		mat.vertex_color_is_srgb = true
		mat.cull_mode = BaseMaterial3D.CULL_DISABLED

		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		mesh.surface_set_material(0, mat)
		var quad := MeshInstance3D.new()
		quad.mesh = mesh
		quad.position = Vector3(cx, cy, 0.0)
		add_child(quad)
		var rect := _rect_px(cx, cy, 1.0, 1.0)
		quads.append([rect[0], rect[1], rect[2], rect[3], _col8(color)])
	_rows["C"] = {"quads": quads}


func _build_row_d() -> void:
	var cy := (ROW_D[0] + ROW_D[1]) * 0.5
	var quads: Array = []
	var cx := -5.0
	for c in ROW_D_FIRST:
		quads.append(_d_quad(cx, cy, c, false))
		cx += 2.0
	for c in ROW_D_FOG_DISABLED:
		quads.append(_d_quad(cx, cy, c, true))
		cx += 2.0
	_rows["D"] = {"quads": quads}


func _d_quad(cx: float, cy: float, c: Vector3, fog_disabled: bool) -> Array:
	var shader := Shader.new()
	var code := "shader_type spatial; render_mode unshaded%s; uniform vec3 c; void fragment(){ ALBEDO = c; }" % (", fog_disabled" if fog_disabled else "")
	shader.code = code
	var mat := ShaderMaterial.new()
	mat.shader = shader
	mat.set_shader_parameter("c", c)
	var mesh := QuadMesh.new()
	mesh.size = Vector2(1.0, 1.0)
	mesh.material = mat
	var quad := MeshInstance3D.new()
	quad.mesh = mesh
	quad.position = Vector3(cx, cy, 0.0)
	add_child(quad)
	var rect := _rect_px(cx, cy, 1.0, 1.0)
	return [rect[0], rect[1], rect[2], rect[3], {"c": [c.x, c.y, c.z], "fog_disabled": fog_disabled}]


func _build_row_e() -> void:
	var cy := (ROW_E[0] + ROW_E[1]) * 0.5
	var n := ROW_E_BASE.size()
	var quads: Array = []
	var overlays: Array = []
	for i in n:
		var cx := _xpos(i, n)
		var base := StandardMaterial3D.new()
		base.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		base.albedo_color = ROW_E_BASE[i]
		var mesh := QuadMesh.new()
		mesh.size = Vector2(1.0, 1.0)
		mesh.material = base
		var bq := MeshInstance3D.new()
		bq.mesh = mesh
		bq.position = Vector3(cx, cy, 0.0)
		add_child(bq)
		quads.append([_rect_px(cx, cy, 1.0, 1.0), _col8(ROW_E_BASE[i])])

		var ov := StandardMaterial3D.new()
		ov.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		ov.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		ov.albedo_color = Color8(40, 80, 200, 128)
		var om := QuadMesh.new()
		om.size = Vector2(1.0, 1.0)
		om.material = ov
		var oq := MeshInstance3D.new()
		oq.mesh = om
		oq.position = Vector3(cx, cy, 0.5)
		add_child(oq)
		overlays.append([_rect_px(cx, cy, 1.0, 1.0), _col8(Color8(40, 80, 200, 128))])
	_rows["E"] = {"quads": quads, "overlays": overlays}


func _build_row_f() -> void:
	var cy := (ROW_F[0] + ROW_F[1]) * 0.5
	var n := 8
	var quads: Array = []
	for i in n:
		var cx := _xpos(i, n)
		var lit_color: Color = ROW_F_COLORS[i % 4]
		var mat := StandardMaterial3D.new()
		mat.albedo_color = lit_color
		if i >= 4:
			mat.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX
		var mesh := QuadMesh.new()
		mesh.size = Vector2(1.0, 1.0)
		mesh.material = mat
		var quad := MeshInstance3D.new()
		quad.mesh = mesh
		quad.position = Vector3(cx, cy, 0.0)
		add_child(quad)
		var rect := _rect_px(cx, cy, 1.0, 1.0)
		quads.append([rect[0], rect[1], rect[2], rect[3], _col8(lit_color), "per_vertex" if i >= 4 else "per_pixel"])
	_rows["F"] = {"quads": quads}


func _col8(c: Color) -> Array:
	return [int(round(c.r * 255.0)), int(round(c.g * 255.0)), int(round(c.b * 255.0))]


# PROOF_BENCH=<frames>: time full screens instead of rendering the cases. Uncapped, V-Sync off;
# for each material, two full-screen quads, frames timed after a 60-frame warm-up; one
# "bench:" line per material. Driver-level sanity only (on llvmpipe it measures the CPU).
func _bench() -> void:
	var frames := maxi(int(OS.get_environment("PROOF_BENCH")), 60)
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	Engine.max_fps = 0
	_make_camera()
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color8(30, 30, 30)
	add_child(env)
	var light := _make_directional_light()
	var mats := {}
	var unshaded := StandardMaterial3D.new()
	unshaded.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	unshaded.albedo_color = Color8(42, 37, 34)
	mats["unshaded"] = unshaded
	var lit := StandardMaterial3D.new()
	lit.albedo_color = Color8(200, 100, 50)
	mats["lit"] = lit
	for mname: String in mats:
		var nodes: Array[MeshInstance3D] = []
		for layer in 2:
			var mesh := QuadMesh.new()
			mesh.size = Vector2(W, H)
			mesh.material = mats[mname]
			var q := MeshInstance3D.new()
			q.mesh = mesh
			q.position = Vector3(0.0, 0.0, 0.1 * layer)
			add_child(q)
			nodes.append(q)
		for i in 60:
			await get_tree().process_frame
		var t0 := Time.get_ticks_usec()
		for i in frames:
			await get_tree().process_frame
		var ms := float(Time.get_ticks_usec() - t0) / 1000.0 / float(frames)
		print("bench: material=%s layers=2 frames=%d avg_ms=%.3f ir_epilogue='%s'" % [mname, frames, ms, OS.get_environment("IR_EPILOGUE")])
		for q in nodes:
			q.queue_free()
	light.queue_free()
	get_tree().quit(0)
