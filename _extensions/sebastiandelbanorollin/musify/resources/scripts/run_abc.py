# =============================================================================
# MUSIFY ABC PROCESSING ENGINE
# This script handles the conversion of ABC notation into visual (SVG) and 
# audible (MIDI/WAV/WebM) assets. It orchestrates external tools like:
# - abc2svg: Converts ABC notation to SVG images.
# - abc2midi: Converts ABC notation to MIDI files.
# - fluidsynth: Renders MIDI files into high-quality WAV audio.
# - ffmpeg: Compresses WAV audio into optimized WebM (Opus) format.
# =============================================================================

import os
import hashlib
import logging
import re
import subprocess
import shlex
import shutil
import loggingUtils  # Custom utility module for logging and subprocess management

def sanitize_abc_code(code):
    # Ensure there is a K: line in the header (required by abc2svg)
    lines = code.splitlines()
    has_k = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('K:') or stripped.startswith('k:'):
            has_k = True
            break
    
    if not has_k:
        # We need to insert a default K:C line before the first music line.
        # The first music line is the first line that is not empty, 
        # not a comment (starts with %), and does not start with a header field letter and colon (e.g. T:, M:, L:).
        inserted = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith('%'):
                continue
            # Check if it is a header line (e.g. X:1, T:Title, etc.)
            if re.match(r'^[A-Za-z]:', stripped):
                continue
            # It's a music line! Insert K:C before it.
            lines.insert(i, "K:C")
            inserted = True
            break
        if not inserted:
            # If no music line was found (empty tune), just append K:C
            lines.append("K:C")
        code = "\n".join(lines)
    return code

def run_abc(code, file_name="", image_dir="", audio_dir="", log_file="output/log/abc.log", use_cache=True,
            bin_abc2svg="abcnode", bin_abc2midi="abc2midi", 
            bin_fluidsynth="fluidsynth", bin_ffmpeg="ffmpeg", sf2_path="", 
            options=""):
    """
    Main entry point for processing an ABC code block.
    """
    
    # Initialize logging with local INFO levels for clarity during rendering
    loggingUtils.setup_logging(log_file=log_file, file_level=logging.INFO, console_level=logging.INFO)
    
    # Sanitize options to convert smart typography dashes back to hyphens
    if options:
        options = options.replace("–", "--").replace("—", "---")

    # Sanitize ABC code to ensure a K: field is present in the header
    code = sanitize_abc_code(code)

    result = {
        "log": "",
        "image_path": None,
        "audio_path": None
    }

    # Resolve logical directories into physical paths or skip if disabled
    image_dir = loggingUtils.resolve_output_directory(image_dir, "cache/images", "image directory")
    audio_dir = loggingUtils.resolve_output_directory(audio_dir, "cache/audio", "audio directory")

    # Generate a unique filename based on the ABC code hash if no name was provided
    if not file_name:
        file_name = hashlib.sha1(code.encode()).hexdigest()[:10]
    
    logging.info(f"{loggingUtils.get_log_context(0)}: Target file name base: {file_name}")

    # -------------------------------------------------------------------------
    # PART 1: VISUAL GENERATION (SVG)
    # -------------------------------------------------------------------------
    if image_dir:
        logging.info("--- IMAGE GENERATION START (Renderer: abc2svg) ---")
        file_path = os.path.join(image_dir, file_name)
        abc_filename_path = f"{file_path}.abc"
        svg_filename_path = f"{file_path}.svg"

        # Only generate if the code has changed or the file is missing
        if check_if_file_generation_needed(code, svg_filename_path, use_cache):
            
            # Write the ABC code to a file
            with open(abc_filename_path, "w", encoding="utf-8") as f:
                f.write(code)
            
            # Use abc2svg (usually via abcnode wrapper)
            # Options must precede the input file path for proper CLI argument parsing by tosvg.js
            opts_list = []
            if "pagewidth" not in options:
                opts_list.append("--pagewidth 25.2cm")
            if "vocalfont" not in options:
                opts_list.append('--vocalfont "sans-serif 11"')
            if "stretchlast" not in options:
                opts_list.append("--stretchlast 1")
            if "scale" not in options:
                opts_list.append("--scale 1.0")
            if "leftmargin" not in options:
                opts_list.append("--leftmargin 0")
            if "rightmargin" not in options:
                opts_list.append("--rightmargin 0")
            if "topmargin" not in options:
                opts_list.append("--topmargin 0")
            if "botmargin" not in options:
                opts_list.append("--botmargin 0")
            
            if options:
                opts_list.append(options)
            
            opts_str = " ".join(opts_list)
            cmd = f"{bin_abc2svg} tosvg.js {opts_str} {abc_filename_path}"
            
            logging.info(f"Executing abc2svg: {cmd}")
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True, shell=True)
                
                # Extract only the entire <svg>...</svg> block from the output (greedy match to capture nested SVGs)
                full_output = res.stdout
                svg_match = re.search(r'(<svg.*</svg>)', full_output, re.DOTALL)
                
                if svg_match:
                    with open(svg_filename_path, "w", encoding="utf-8") as f:
                        f.write(svg_match.group(1))
                    logging.info("abc2svg SVG extracted successfully.")
                else:
                    with open(svg_filename_path, "w", encoding="utf-8") as f:
                        f.write(full_output)
                    logging.warning("abc2svg completed but <svg> tag not found; wrote full output.")
            except Exception as e:
                logging.error(f"abc2svg failed: {e}")
                result["image_path"] = None

            # Optional: Optimize SVG using SVGO (if installed)
            if shutil.which("svgo"):
                commandSVGO = ["svgo", "--pretty", "--eol", "lf", "--indent", "0", "--no-color", svg_filename_path]
                loggingUtils.run_command(commandSVGO, "SVGO")
            else:
                logging.info("SVGO not found; skipping optional optimization.")

            # RECOLORING & ID PREFIXING FOR EMBEDDING SUPPORT
            logging.info("Preparing SVG for seamless HTML embedding")
            if os.path.exists(svg_filename_path):
                with open(svg_filename_path, 'r', encoding="utf-8") as f:
                     svg_content = f.read()

                # 1. Remove hardcoded color attributes from the root <svg> tag
                modified_content = re.sub(r'<svg([^>]*)color="[^"]*"([^>]*)>', r'<svg\1\2>', svg_content)
                
                # 2. Convert fixed width/height to viewBox for responsiveness on the root <svg> tag only
                svg_tag_match = re.search(r'(<svg[^>]*>)', modified_content)
                if svg_tag_match:
                    svg_tag = svg_tag_match.group(1)
                    width_match = re.search(r'width="([\d\.]+)(?:p[xt])?"', svg_tag)
                    height_match = re.search(r'height="([\d\.]+)(?:p[xt])?"', svg_tag)
                    if width_match and height_match:
                        width = width_match.group(1)
                        height = height_match.group(1)
                        viewbox_str = f'viewBox="0 0 {width} {height}"'
                        # Replace width with viewBox and remove height from the root tag only
                        new_svg_tag = re.sub(r'width="[\d\.]+(?:p[xt])?"', viewbox_str, svg_tag)
                        new_svg_tag = re.sub(r'height="[\d\.]+(?:p[xt])?"', '', new_svg_tag)
                        modified_content = modified_content.replace(svg_tag, new_svg_tag, 1)
                        logging.info(f"Converted root SVG dimensions to {viewbox_str}")

                # 3. Prefix IDs to avoid collisions when embedding multiple SVGs in one page
                prefix = file_name + "_"
                modified_content = re.sub(r'id="([^"]+)"', r'id="' + prefix + r'\1"', modified_content)
                modified_content = re.sub(r'href="#([^"]+)"', r'href="#' + prefix + r'\1"', modified_content)
                modified_content = re.sub(r'url\(#([^"]+)\)', r'url(#' + prefix + r'\1)', modified_content)

                # 4. Define the adaptive style and inject it into the existing style block
                if '<style' in modified_content:
                    rules_to_insert = "\n  svg { color: inherit; }\n  .fill { fill: currentColor; }\n  .stroke { stroke: currentColor; fill: none; }\n  text { fill: currentColor; }"
                    modified_content = re.sub(r'(<style[^>]*>)', r'\1' + rules_to_insert, modified_content, count=1)
                else:
                    adaptive_style = """<style>
  svg { color: inherit; }
  .fill { fill: currentColor; }
  .stroke { stroke: currentColor; fill: none; }
  text { fill: currentColor; }
</style>"""
                    modified_content = re.sub(r'(<svg[^>]*>)', r'\1' + adaptive_style, modified_content)

                # 5. Prefix CSS classes and style selectors to avoid global collisions in HTML inline embedding
                def prefix_class_attr(match):
                    classes = match.group(1).split()
                    prefixed_classes = [f"{prefix}{c}" for c in classes]
                    return f'class="{" ".join(prefixed_classes)}"'

                modified_content = re.sub(r'class="([^"]+)"', prefix_class_attr, modified_content)

                def prefix_style_block(style_match):
                    style_content = style_match.group(1)
                    # Prefix class selectors starting with . followed by a letter (to avoid matching decimals)
                    prefixed_style = re.sub(r'\.([a-zA-Z][a-zA-Z0-9_-]*)', r'.' + prefix + r'\1', style_content)
                    return f"<style>{prefixed_style}</style>"

                modified_content = re.sub(r'<style[^>]*>(.*?)</style>', prefix_style_block, modified_content, flags=re.DOTALL)

                with open(svg_filename_path, 'w', encoding="utf-8") as f:
                    f.write(modified_content)
                
                result["image_path"] = svg_filename_path
        else:
            logging.info(f"Using cached image at {svg_filename_path}")
            result["image_path"] = svg_filename_path

    # -------------------------------------------------------------------------
    # PART 2: AUDIO GENERATION (WebM)
    # -------------------------------------------------------------------------
    if audio_dir:
        logging.info("--- AUDIO GENERATION START ---")
        file_path = os.path.join(audio_dir, file_name)
        abc_filename_path = os.path.join(audio_dir, f"{file_name}.abc")
        mid_filename_path = os.path.join(audio_dir, f"{file_name}.mid")
        wav_filename_path = os.path.join(audio_dir, f"{file_name}.wav")
        webm_filename_path = os.path.join(audio_dir, f"{file_name}.webm")

        if check_if_file_generation_needed(code, webm_filename_path, use_cache):
            with open(abc_filename_path, "w", encoding="utf-8") as f:
                f.write(code)

            # STEP A: ABC to MIDI
            cmd = [bin_abc2midi, abc_filename_path, "-o", mid_filename_path]
            if not loggingUtils.run_command(cmd, "abc2midi"):
                result["audio_path"] = None

            # STEP B: MIDI to WAV
            if not sf2_path:
                # Priority: 1. Environment Variable, 2. Hardcoded fallback
                sf2_path = os.environ.get("MUSIFY_SF2_PATH") or "~/.local/share/soundfonts/timbresOfHeaven4.00.sf2"
            
            sf2_path = os.path.expandvars(os.path.expanduser(sf2_path))
            logging.info(f"Using SoundFont: {sf2_path}")
            cmd = [bin_fluidsynth, "-n", "-i", "-F", wav_filename_path, sf2_path, mid_filename_path]
            if not loggingUtils.run_command(cmd, "fluidsynth", timeout=30):
                result["audio_path"] = None

            # STEP C: WAV to WEBM (Opus)
            cmd = [bin_ffmpeg, "-y", "-i", wav_filename_path, "-c:a", "libopus", "-b:a", "64k", webm_filename_path]
            if not loggingUtils.run_command(cmd, "ffmpeg"):
                result["audio_path"] = None
            
            result["audio_path"] = webm_filename_path
        else:
            logging.info(f"Using cached audio at {webm_filename_path}")
            result["audio_path"] = webm_filename_path

    return result

def check_if_file_generation_needed(code, output_filename, use_cache):
    """
    Determines if we need to regenerate an asset.
    """
    if not use_cache:
        return True
    
    if not os.path.exists(output_filename):
        logging.info(f"File {output_filename} missing. Generation needed.")
        return True
        
    directory = os.path.dirname(output_filename)
    base_name = os.path.splitext(os.path.basename(output_filename))[0]
    abc_filename = os.path.join(directory, base_name + ".abc")
    
    if not os.path.exists(abc_filename):
        logging.info(f"Source {abc_filename} missing. Generation needed.")
        return True

    try:
        with open(abc_filename, "r", encoding="utf-8") as f:
            existing_code = f.read()
            
        if existing_code != code:
            logging.info("ABC code changed. Generation needed.")
            return True
            
        if os.path.getmtime(abc_filename) > os.path.getmtime(output_filename):
            logging.info("Source file newer than output. Generation needed.")
            return True
            
        return False
    except Exception as e:
        logging.error(f"Error checking cache: {e}")
        return True
