# Musify: Quarto Extension for Music Notation

Musify is a [Quarto](https://quarto.org/) extension that allows you to embed high-quality music notation and audio directly into your documents using [ABC notation](https://abcnotation.com/).

It converts ABC code blocks into:
- **Visuals**: Scalable Vector Graphics (SVG) using `abcm2ps` or `abc2svg`.
- **Audio**: WebM files generated via `abc2midi`, `fluidsynth`, and `ffmpeg`.

## Features

- **Integrated Audio Player**: Automatically generates and embeds an HTML5 audio player.
- **Customizable Rendering**: Choose between multiple renderers and pass custom options.
- **Smart Metadata**: Configure global settings in `_quarto.yml` or override them per code block.
- **Dependency Tracking**: Includes a built-in checker to ensure your environment is ready.

## Installation

To install the extension in your Quarto project, run:

```bash
quarto add sebastiandelbanorollin/musify
```

## System Dependencies

Musify relies on several external tools. Ensure these are installed on your system:

- **ABC Tools**: `abcm2ps` (or `abcnode` for `abc2svg`) and `abc2midi`.
- **Audio Generation**: `fluidsynth` and `ffmpeg`.
- **Python 3**: Used for backend processing.
- **SoundFont**: A high-quality SoundFont (e.g., *Timbres of Heaven*) is required for audio synthesis.

### SoundFont Setup
By default, Musify looks for a SoundFont at
`~/.local/share/soundfonts/timbresOfHeaven4.00.sf2`. You can customize this in
your metadata:

```yaml
musify:
  sf2-path: "/path/to/your/font.sf2"
```

## Usage

Add a code block with the `{abc}` class to your Quarto document:

```markdown
---
title: "My Music Sheet"
filters:
  - musify
---

## Example Piece

{abc scoreName="my_song" visual="true" audio="true" fig-cap="A simple melody"}
X:1
T:Simple Scale
M:4/4
L:1/4
K:C
C D E F | G A B c |
```

### Options

| Attribute | Description | Default |
|-----------|-------------|---------|
| `scoreName` | Base name for generated files | SHA1 hash |
| `visual` | Enable SVG generation | `false` |
| `audio` | Enable Audio generation | `false` |
| `fig-cap` | Caption for the music figure | `""` |
| `renderer` | Rendering engine (`abcm2ps` or `abc2svg`) | `abcm2ps` |
| `image-dir`| Directory for SVG output | `resources/images` |
| `audio-dir`| Directory for audio output | `resources/audio` |

## Configuration

You can set global defaults in your `_quarto.yml`:

```yaml
musify:
  renderer: "abcm2ps"
  image-dir: "assets/music/images"
  audio-dir: "assets/music/audio"
  bin-ffmpeg: "/usr/local/bin/ffmpeg"
```

## License

This project is licensed under the [MIT License](LICENSE).
