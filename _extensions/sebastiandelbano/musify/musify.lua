-- =============================================================================
-- MUSIFY QUARTO EXTENSION (Lua Filter & Shortcodes)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- HELPER FUNCTIONS
-- -----------------------------------------------------------------------------

local function read_file(path)
  local file = io.open(path, "rb")
  if not file then return nil end
  local content = file:read("*all")
  file:close()
  return content
end

local function file_exists(path)
  local f = io.open(path, "r")
  if f then
    f:close()
    return true
  end
  return false
end

local function trimws(s)
  return s:match("^%s*(.-)%s*$")
end

local function base64_encode(data)
  local b = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
  return ((data:gsub('.', function(x)
    local r,b='',x:byte()
    for i=8,1,-1 do r=r..(b%2^i-b%2^(i-1)>0 and '1' or '0') end
    return r;
  end)..'0000'):gsub('%d%d%d?%d?%d?%d?', function(x)
    if (#x < 6) then return '' end
    local c=0
    for i=1,6 do c=c+(x:sub(i,i)=='1' and 2^(6-i) or 0) end
    return b:sub(c+1,c+1)
  end)..({ '', '==', '=' })[#data%3+1])
end

-- Robust stringify helper
local function stringify(el)
  if type(el) == "string" then return el end
  if el == nil then return "" end
  if quarto and quarto.utils and quarto.utils.stringify then
    return quarto.utils.stringify(el)
  end
  if pandoc and pandoc.utils and pandoc.utils.stringify then
    return pandoc.utils.stringify(el)
  end
  return tostring(el)
end

local is_windows = package.config:sub(1,1) == "\\"

local function make_dir(path)
  if is_windows then
    local win_path = path:gsub("/", "\\")
    os.execute("if not exist " .. string.format("%q", win_path) .. " mkdir " .. string.format("%q", win_path))
  else
    os.execute("mkdir -p " .. string.format("%q", path))
  end
end

local function to_py_str(str)
  if not str then return "''" end
  local escaped = str:gsub("\\", "\\\\"):gsub("'", "\\'")
  return "'" .. escaped .. "'"
end

local python_cmd = nil
local function get_python_cmd()
  if python_cmd then return python_cmd end
  local cmds = is_windows and {"python", "python3"} or {"python3", "python"}
  for _, cmd in ipairs(cmds) do
    local dev_null = is_windows and "nul" or "/dev/null"
    local run_status = os.execute(cmd .. " --version >" .. dev_null .. " 2>&1")
    if run_status then
      python_cmd = cmd
      return python_cmd
    end
  end
  python_cmd = is_windows and "python" or "python3"
  return python_cmd
end

-- -----------------------------------------------------------------------------
-- FILTER LOGIC
-- -----------------------------------------------------------------------------


local dependency_check_done = false

local function get_meta_string(m, key, default)
  if m and m[key] then
    return stringify(m[key])
  end
  return default
end
-- This is the callback function that quarto will call for each code block
local function CodeBlock(el)
  if el.classes:includes('abc') then
    local musify_meta = {}
    if quarto and quarto.metadata then
      musify_meta = quarto.metadata.get("musify") or {}
    end
    if quarto and quarto.doc and quarto.doc.is_format("html") then
      quarto.doc.add_html_dependency({
        name = "musify-assets",
        version = "1.0.0",
        src = quarto.utils.resolve_path("."),
        stylesheets = {"resources/css/musify.css"},
        resources = {"resources/fonts/Bravura.woff2"}
      })
    end
    local default_abc2svg = is_windows and "abc2svg" or "abcnode"
    local bin_abc2svg  = get_meta_string(musify_meta, 'bin-abc2svg', default_abc2svg)
    local bin_abc2midi = get_meta_string(musify_meta, 'bin-abc2midi', "abc2midi")
    local bin_fluidsynth = get_meta_string(musify_meta, 'bin-fluidsynth', "fluidsynth")
    local bin_ffmpeg   = get_meta_string(musify_meta, 'bin-ffmpeg', "ffmpeg")
    local sf2_path     = get_meta_string(musify_meta, 'sf2-path', "")
    local extra_options = get_meta_string(musify_meta, 'options', "--musicfont Bravura")
    local target_image_dir = get_meta_string(musify_meta, 'image-dir', "cache/images")
    local target_audio_dir = get_meta_string(musify_meta, 'audio-dir', "cache/audio")

    local python_script_dir = quarto.utils.resolve_path("resources/scripts")
    if not dependency_check_done then
      local check_cmd = string.format(
        "%s -c \"import sys; sys.path.append(%s); import check_dependencies; " ..
        "check_dependencies.check_dependencies(abc2svg=%s, abc2midi=%s, fluidsynth=%s, ffmpeg=%s, sf2_path=%s)\"",
        get_python_cmd(),
        to_py_str(python_script_dir),
        to_py_str(bin_abc2svg),
        to_py_str(bin_abc2midi),
        to_py_str(bin_fluidsynth),
        to_py_str(bin_ffmpeg),
        to_py_str(sf2_path)
      )
      os.execute(check_cmd)
      dependency_check_done = true
    end

    local file_name = el.attributes['scoreName'] or el.attributes['codeName'] or ""
    local visual_enabled = el.attributes['visual'] or "false"
    local audio_enabled = el.attributes['audio'] or "false"
    local fig_caption = el.attributes['fig-cap'] or ""
    local options_override  = el.attributes['options'] or extra_options
    local eval_block = true
    local echo_block = true

    target_image_dir = el.attributes['image-dir'] or target_image_dir
    target_audio_dir = el.attributes['audio-dir'] or target_audio_dir
    if el.attributes['eval'] == "false" or el.attributes['eval'] == "FALSE" then eval_block = false end
    if el.attributes['echo'] == "false" or el.attributes['echo'] == "FALSE" then echo_block = false end

    local clean_abc_lines = {}
    for line in string.gmatch(el.text, "[^\r\n]+") do
      local key, val = string.match(line, "^%s*#|%s*([^:]+):%s*(.*)$")
      if key then
        key = trimws(key)
        val = trimws(val):gsub("^[\"']", ""):gsub("[\"']$", "")
        if key == "scoreName" or key == "codeName" then file_name = val
        elseif key == "visual" then visual_enabled = val
        elseif key == "audio" then audio_enabled = val
        elseif key == "fig-cap" then fig_caption = val
        elseif key == "options" then options_override = val
        elseif key == "image-dir" then target_image_dir = val
        elseif key == "audio-dir" then target_audio_dir = val
        elseif key == "eval" and (val == "false" or val == "FALSE") then eval_block = false
        elseif key == "echo" and (val == "false" or val == "FALSE") then echo_block = false
        end
      else
        table.insert(clean_abc_lines, line)
      end
    end
    local clean_abc_text = table.concat(clean_abc_lines, "\n")
    if not eval_block then return el end

    make_dir(target_image_dir)
    make_dir(target_audio_dir)
    if file_name == "" then file_name = pandoc.sha1(clean_abc_text):sub(1, 10) end

    local tmp_abc_path = target_image_dir .. "/tmp_" .. file_name .. ".abc"
    local f_abc = io.open(tmp_abc_path, "w")
    f_abc:write(clean_abc_text)
    f_abc:close()

    local visual_dir = (visual_enabled == "true" or visual_enabled == "TRUE") and target_image_dir or ""
    local audio_dir = (audio_enabled == "true" or audio_enabled == "TRUE") and target_audio_dir or ""
    local cmd = string.format(
      "%s -c \"import sys; sys.path.append(%s); import run_abc; " ..
      "f=open(%s, 'r', encoding='utf-8'); code=f.read(); f.close(); " ..
      "run_abc.run_abc(code, file_name=%s, image_dir=%s, audio_dir=%s, " ..
      "bin_abc2svg=%s, bin_abc2midi=%s, bin_fluidsynth=%s, bin_ffmpeg=%s, sf2_path=%s, options=%s)\"",
      get_python_cmd(),
      to_py_str(python_script_dir),
      to_py_str(tmp_abc_path),
      to_py_str(file_name),
      to_py_str(visual_dir),
      to_py_str(audio_dir),
      to_py_str(bin_abc2svg),
      to_py_str(bin_abc2midi),
      to_py_str(bin_fluidsynth),
      to_py_str(bin_ffmpeg),
      to_py_str(sf2_path),
      to_py_str(options_override)
    )
    os.execute(cmd)
    os.remove(tmp_abc_path)

    local generated_svg = target_image_dir .. "/" .. file_name .. ".svg"
    local generated_webm = target_audio_dir .. "/" .. file_name .. ".webm"
    local final_payload = ""

    if (visual_enabled == "true" or visual_enabled == "TRUE") and file_exists(generated_svg) then
      if quarto.doc.is_format("html") then
        local svg_raw_content = read_file(generated_svg)
        if svg_raw_content then
          local svg_embedded = svg_raw_content:gsub('^<%?xml[^>]+%>', ''):gsub('^<!DOCTYPE[^>]+%>', '')
          final_payload = final_payload .. string.format(
            '<figure style="margin: 1rem 0;" class="figure">\n' ..
            '  <div class="musify-svg-container" style="max-width: 100%%; height: auto;">\n' ..
            '    %s\n' ..
            '  </div>\n' ..
            '  <figcaption>%s</figcaption>\n' ..
            '</figure>\n',
            svg_embedded, fig_caption
          )
        end
      else
        final_payload = final_payload .. string.format(
          '<figure style="margin: 1rem 0;" class="figure">\n' ..
          '  <img src="%s" alt="%s" style="max-width: 100%%; height: auto;" class="figure-img">\n' ..
          '  <figcaption>%s</figcaption>\n' ..
          '</figure>\n',
          generated_svg, fig_caption, fig_caption
        )
      end
    end

    if (audio_enabled == "true" or audio_enabled == "TRUE") and file_exists(generated_webm) then
      local audio_raw_content = read_file(generated_webm)
      if audio_raw_content then
        local audio_base64 = base64_encode(audio_raw_content)
        local audio_data_uri = "data:audio/webm;base64," .. audio_base64
        local audio_html = string.format(
          '<div class="musify-audio-container" style="margin-top: 1.5rem; margin-bottom: 1.5rem; display: block;">\n' ..
          '  <audio controls preload="none" style="width: 100%%; max-width: 400px; display: block;">\n' ..
          '    <source src="%s" type="audio/webm">\n' ..
          '    Your browser does not support the audio element.\n' ..
          '  </audio>\n' ..
          '</div>\n\n',
          audio_data_uri
        )
        final_payload = final_payload .. "\n" .. audio_html .. "\n\n"
      end
    end

    el.text = clean_abc_text
    local out_blocks = {}
    if echo_block then table.insert(out_blocks, el) end
    if final_payload ~= "" then table.insert(out_blocks, pandoc.RawBlock('html', final_payload)) end
    return out_blocks
  end
  return el
end
-- -----------------------------------------------------------------------------
-- EXPORTS
-- -----------------------------------------------------------------------------
return {
  --- this defines a function called musify
  --- This return instruction returns a table with the function musify, Meta, and CodeBlock.
  --- These are special named functions that quarto will use (callback functions).
  --- {musify=..., Meta=..., CodeBlock=...} is a table, the keys are the names, and the values
  --- are the functions.
  ['musify'] = function(args, kwargs, meta)
    local arg1 = stringify(args[1])
    if arg1 == "icon" then
      -- Resolve paths relative to the extension directory
      local light_icon_path = quarto.utils.resolve_path("resources/images/musifySansText.svg")
      local dark_icon_path = quarto.utils.resolve_path("resources/images/musifySansTextDark.svg")
      local light_base64 = ""
      local dark_base64 = ""
      if file_exists(light_icon_path) then
        local content = read_file(light_icon_path)
        light_base64 = "data:image/svg+xml;base64," .. base64_encode(content)
      end
      if file_exists(dark_icon_path) then
        local content = read_file(dark_icon_path)
        dark_base64 = "data:image/svg+xml;base64," .. base64_encode(content)
      end
      local html = string.format([[
<span class="musify-inline-icon" style="display: inline-block; vertical-align: middle;">
<img src="%s" class="quarto-light-logo" style="height: 1.2em; width: auto; display: inline-block; vertical-align: middle; margin-right: 8px;">
<img src="%s" class="quarto-dark-logo" style="height: 1.2em; width: auto; display: none; vertical-align: middle; margin-right: 8px;">
</span>]], light_base64, dark_base64)
      return pandoc.RawInline('html', html)
    end
    if arg1 == "logo" then
      -- Resolve paths relative to the extension directory
      local light_logo_path = quarto.utils.resolve_path("resources/images/musify.svg")
      local dark_logo_path = quarto.utils.resolve_path("resources/images/musifyDark.svg")
      local light_base64 = ""
      local dark_base64 = ""
      if file_exists(light_logo_path) then
        local content = read_file(light_logo_path)
        light_base64 = "data:image/svg+xml;base64," .. base64_encode(content)
      end
      if file_exists(dark_logo_path) then
        local content = read_file(dark_logo_path)
        dark_base64 = "data:image/svg+xml;base64," .. base64_encode(content)
      end
      local html = string.format([[
<div class="musify-top-logo">
<!-- Light mode logo (hidden in dark mode) -->
<img src="%s" class="quarto-light-logo">
<!-- Dark mode logo (hidden in light mode) -->
<img src="%s" class="quarto-dark-logo">
</div>
<style>
.musify-top-logo {
  position: absolute;
  top: 10px;
  right: 20px;
  z-index: 100;
}
.musify-top-logo img {
  height: 256px;
  width: auto;
}
@media (max-width: 768px) {
  .musify-top-logo {
    position: relative;
    top: auto;
    right: auto;
    margin: 10px auto 20px auto;
    display: flex;
    justify-content: center;
  }
  .musify-top-logo img {
    height: 120px !important;
  }
}
/* Quarto dynamically adds these classes to the <body> tag when switching themes */
body.quarto-light .quarto-light-logo { display: block !important; }
body.quarto-light .quarto-dark-logo { display: none !important; }
body.quarto-dark .quarto-light-logo { display: none !important; }
body.quarto-dark .quarto-dark-logo { display: block !important; }
</style>]], light_base64, dark_base64)
      return pandoc.RawInline('html', html)
    end

    if arg1 == "icon2" then
      local light_icon_path = quarto.utils.resolve_path("resources/images/musifySansText.svg")
      local dark_icon_path = quarto.utils.resolve_path("resources/images/musifySansTextDark.svg")
      local light_svg = file_exists(light_icon_path) and read_file(light_icon_path) or ""
      local dark_svg = file_exists(dark_icon_path) and read_file(dark_icon_path) or ""
      -- We use standard .. operator concatenation to safely sandwich the raw XML text
      local html = [[
<span class="musify-inline-icon" style="display: inline-block; vertical-align: middle;">
<span class="quarto-light-logo" style="height: 1.2em; display: inline-block; vertical-align: middle; margin-right: 8px;">]]
.. light_svg .. [[</span>
<span class="quarto-dark-logo" style="height: 1.2em; display: none; vertical-align: middle; margin-right: 8px;">]]
.. dark_svg .. [[</span>
</span>
<style>
/* Force the raw inline SVG elements to scale nicely inside their parent spans */
.musify-inline-icon .quarto-light-logo svg,
.musify-inline-icon .quarto-dark-logo svg {
  height: 100%;
  width: auto;
  display: inline-block;
  vertical-align: middle;
}
</style>]]
      return pandoc.RawInline('html', html)
    end
    if arg1 == "logo2" then
      local light_logo_path = quarto.utils.resolve_path("resources/images/musify.svg")
      local dark_logo_path = quarto.utils.resolve_path("resources/images/musifyDark.svg")
      local light_svg = file_exists(light_logo_path) and read_file(light_logo_path) or ""
      local dark_svg = file_exists(dark_logo_path) and read_file(dark_logo_path) or ""
      local html = [[
<div class="quarto-light-logo" style="width: 10%!important; display: block;">]]
.. light_svg .. [[</div>
<div class="quarto-dark-logo" style="width: 10%!important;  display: none;">]]
.. dark_svg .. [[</div>
</div>
<style>
/* Quarto dynamically targets these wrappers when switching themes */
body.quarto-light .quarto-light-logo { display: block !important; }
body.quarto-light .quarto-dark-logo { display: none !important; }
body.quarto-dark .quarto-light-logo { display: none !important; }
body.quarto-dark .quarto-dark-logo { display: block !important; }
</style>]]
      return pandoc.RawInline('html', html)
    end
  end,
  -- Your existing AST callbacks
  CodeBlock = CodeBlock
}


