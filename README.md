# Calibre Plugins

Calibre plugins for [CrossPoint Reader](https://github.com/crosspoint-reader).

## Plugins

### CrossPoint Reader

A wireless device plugin that uploads EPUB files to CrossPoint Reader over WebSocket. The plugin auto-discovers devices on the local network via UDP broadcast.

See [crosspoint_reader/README.md](crosspoint_reader/README.md) for protocol details and configuration.

## Installation

Download the latest release from the [releases page](https://github.com/crosspoint-reader/calibre-plugins/releases), then in Calibre: **Preferences > Plugins > Load plugin from file**.

## Development

### Setup

```sh
# Build and install the plugin into Calibre
make install

# List all installed plugins
make list

# Remove the plugin
make remove
```

See [`calibre-customize` docs](https://manual.calibre-ebook.com/generated/en/calibre-customize.html) for more options.

### Project structure

```
crosspoint_reader/
  __init__.py   # Plugin entry point
  driver.py     # Device driver (discovery, upload, delete)
  ws_client.py  # WebSocket client and UDP discovery
  config.py     # Settings UI and preferences
  log.py        # Logging utilities
```

## License

[MIT](LICENSE)
