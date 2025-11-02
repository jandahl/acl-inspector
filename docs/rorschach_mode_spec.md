────────────────────────

1. Human-level description
   ────────────────────────
   “Rorschach mode” is a full-viewport panel that shows a perfectly vertically mirrored inkblot. The pattern is always moving, but slowly, as if thick ink is being pulled underneath glass. Shapes appear, stretch, then collapse back into new ones. There are no hard resets; one state oozes into the next. The panel respects the site’s color mode:

* in light mode: dark ink on light background
* in dark mode: light ink on dark background

The pattern is high-contrast because a soft procedural field is run through a threshold. The animation feels organic because the field changes over time using low-frequency noise plus a little higher-frequency detail. Motion is mainly vertical, with small lateral turbulence.

Key properties:

* Strict vertical symmetry.
* Continuous morphing (no frame-to-frame popping).
* Mostly 1–3 large “lobes” plus finer detail at edges.
* Occasionally “holds” for a moment when the noise crosses near the threshold.
* Deterministic per session (seeded), but looks random.

────────────────────────
2. Technical model (what the shader does)
────────────────────────
Core idea: compute a time-varying 2D fractal noise field on only half the screen, mirror it, threshold it.

Steps:

1. Normalize fragment coordinate to [0,1] → `uv`.
2. Enforce vertical mirroring:

   * if `uv.x > 0.5` then sample from `1.0 - uv.x`
3. Build a time-varying domain:

   * `domain = mirroredUV * scale + vec2(0.0, time * baseSpeed)`
   * Optionally add a slight x drift with time.
4. Evaluate fbm (fractal Brownian motion) noise on that domain to get a smooth scalar `n` in [0,1].
5. Shape the field:

   * Center bias: multiply by something that favors center columns, so the blot doesn’t thin out at edges.
6. Threshold:

   * `ink = smoothstep(threshold - edge, threshold + edge, n)`
   * This gives thick center areas and soft edges.
7. Color:

   * if theme = light → ink = dark; bg = light
   * if theme = dark → ink = light; bg = dark
8. Output.

────────────────────────
3. Parameters to expose
────────────────────────
These are the knobs your webapp should be able to pass to the shader:

* `u_time`: seconds since start (float)
* `u_resolution`: vec2(canvasWidth, canvasHeight)
* `u_theme`: 0.0 = light, 1.0 = dark
* `u_scale`: how zoomed-in the noise is, default 2.0–3.0
* `u_speed`: 0.08–0.15 for slow “ink” feel
* `u_threshold`: 0.45–0.55
* `u_edge_softness`: 0.04–0.1
* `u_center_bias`: 0.7–1.2 (to keep mass in the middle)
* `u_seed`: used to offset the domain so each load looks different

That’s enough to make it look deliberate, not wallpaper.

────────────────────────
4. `codex`-style implementation brief
────────────────────────
Goal: client-side WebGL2 full-screen Rorschach inkblot, animated, theme-aware, deterministic-per-session.

#### 4.1 HTML scaffold

```html
<canvas id="rorschach" aria-hidden="true"></canvas>
```

Canvas is positioned by CSS in your app’s preview area.

#### 4.2 JS runtime skeleton

```js
// RORSCHACH MODE RUNTIME
// Target: modern browsers w/ WebGL2
// Responsibilities:
// 1. initGL(canvas)
// 2. createProgram(vertexSrc, fragmentSrc)
// 3. render loop (time-based)
// 4. handle resize + DPR
// 5. pass theme + seed uniforms

(function() {
  const canvas = document.getElementById('rorschach');
  const gl = canvas.getContext('webgl2', { antialias: true, premultipliedAlpha: false });
  if (!gl) {
    // TODO: implement 2D canvas fallback or hide feature
    return;
  }

  const vertexSrc = `#version 300 es
  precision highp float;
  const vec2 verts[6] = vec2[6](
    vec2(-1.0, -1.0),
    vec2( 1.0, -1.0),
    vec2(-1.0,  1.0),
    vec2(-1.0,  1.0),
    vec2( 1.0, -1.0),
    vec2( 1.0,  1.0)
  );
  void main() {
    gl_Position = vec4(verts[gl_VertexID], 0.0, 1.0);
  }`;

  const fragmentSrc = `#version 300 es
  precision highp float;

  out vec4 outColor;

  uniform vec2 u_resolution;
  uniform float u_time;
  uniform float u_theme;       // 0.0 = light, 1.0 = dark
  uniform float u_scale;
  uniform float u_speed;
  uniform float u_threshold;
  uniform float u_edge_softness;
  uniform float u_center_bias;
  uniform vec2 u_seed;

  // Simple 2D hash
  float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
  }

  // 2D value noise
  float valueNoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);

    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));

    vec2 u = f * f * (3.0 - 2.0 * f);

    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
  }

  // fbm for organic shapes
  float fbm(vec2 p) {
    float total = 0.0;
    float amp = 0.5;
    float freq = 1.0;
    for (int i = 0; i < 5; i++) {
      total += valueNoise(p * freq) * amp;
      freq *= 2.0;
      amp *= 0.5;
    }
    return total;
  }

  void main() {
    // normalize
    vec2 uv = gl_FragCoord.xy / u_resolution.xy;

    // vertical mirror
    float mx = (uv.x <= 0.5) ? uv.x : (1.0 - uv.x);
    vec2 muv = vec2(mx, uv.y);

    // domain warp over time
    float t = u_time * u_speed;
    vec2 domain = muv * u_scale + u_seed + vec2(t * 0.25, t);

    // base field
    float n = fbm(domain);

    // center bias: push value higher near vertical centerline
    float distFromCenter = abs(uv.x - 0.5) * 2.0; // 0 at center, 1 at edges
    float centerMask = pow(1.0 - distFromCenter, u_center_bias);
    n *= (0.65 + 0.35 * centerMask);

    // threshold into ink
    float ink = smoothstep(u_threshold - u_edge_softness, u_threshold + u_edge_softness, n);

    // theme-aware colors
    vec3 lightBg = vec3(0.96);
    vec3 lightInk = vec3(0.05);
    vec3 darkBg = vec3(0.03);
    vec3 darkInk = vec3(0.95);

    vec3 bg = mix(lightBg, darkBg, u_theme);
    vec3 fg = mix(lightInk, darkInk, u_theme);

    vec3 color = mix(bg, fg, ink);

    outColor = vec4(color, 1.0);
  }`;

  function createShader(gl, type, src) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      console.error(gl.getShaderInfoLog(sh));
    }
    return sh;
  }

  const vs = createShader(gl, gl.VERTEX_SHADER, vertexSrc);
  const fs = createShader(gl, gl.FRAGMENT_SHADER, fragmentSrc);
  const prog = gl.createProgram();
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    console.error(gl.getProgramInfoLog(prog));
  }

  const locRes = gl.getUniformLocation(prog, "u_resolution");
  const locTime = gl.getUniformLocation(prog, "u_time");
  const locTheme = gl.getUniformLocation(prog, "u_theme");
  const locScale = gl.getUniformLocation(prog, "u_scale");
  const locSpeed = gl.getUniformLocation(prog, "u_speed");
  const locThreshold = gl.getUniformLocation(prog, "u_threshold");
  const locEdge = gl.getUniformLocation(prog, "u_edge_softness");
  const locCenter = gl.getUniformLocation(prog, "u_center_bias");
  const locSeed = gl.getUniformLocation(prog, "u_seed");

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth * dpr;
    const h = canvas.clientHeight * dpr;
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
    }
  }

  // deterministic-ish per session
  const seedX = Math.random() * 1000.0;
  const seedY = Math.random() * 1000.0;

  let start = performance.now();
  function frame(now) {
    resize();
    const tSec = (now - start) * 0.001;

    gl.useProgram(prog);
    gl.uniform2f(locRes, canvas.width, canvas.height);
    // plug your actual theme getter here:
    const theme = document.documentElement.classList.contains('dark') ? 1.0 : 0.0;
    gl.uniform1f(locTheme, theme);
    gl.uniform1f(locTime, tSec);
    gl.uniform1f(locScale, 3.0);
    gl.uniform1f(locSpeed, 0.12);
    gl.uniform1f(locThreshold, 0.52);
    gl.uniform1f(locEdge, 0.06);
    gl.uniform1f(locCenter, 1.0);
    gl.uniform2f(locSeed, seedX, seedY);

    gl.drawArrays(gl.TRIANGLES, 0, 6);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
```

────────────────────────
5. Why this will read as “Rorschach” to users
────────────────────────

* Perfect vertical mirroring is non-negotiable; humans detect that instantly.
* High-contrast ink vs. paper with soft edges is what sells the “blot on paper.”
* Slow, viscous motion instead of looping sprite or GIF rejects “UI flourish” and reads closer to “living mask.”
* Theme inversion makes it feel like part of the page, not an iframe toy.

────────────────────────
6. What to adjust
────────────────────────

* If it looks too noisy: lower `u_scale` to 2.2 and raise `u_edge_softness` to 0.08.
* If it looks too static: raise `u_speed` to 0.18.
* If it looks too spidery: drop `u_threshold` toward 0.48.
* If you want it more “Watchmen-mask blobby”: increase `u_center_bias` to 1.3 and lower `u_scale` slightly.

