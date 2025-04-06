# Mazda Connected Services for Home Assistant

This is an enhanced fork of the Mazda Connected Services integration for Home Assistant, building upon the work originally started by bdr99. The original code was part of the Home Assistant core integrations before a DMCA takedown notice was issued by Mazda Motor Corporation.

## What's Different in This Fork?

- Enhanced error handling and connection reliability
- Improved support for newer Mazda vehicle models
- Optimized performance with configurable update intervals
- Added additional vehicle metrics and controls
- Optimized health data fetching to eliminate duplicate API calls and prevent connection resets

## Features

- Control door locks and remotely start your engine
- Track your vehicle's location
- Monitor fuel/battery levels, odometer, and other vehicle metrics
- View tire pressure and TPMS warnings
- Receive maintenance alerts and health reports
- View and control climate settings
- Enhanced error handling with improved connection reliability features

## Supported Vehicles

All Mazda vehicles with Mazda Connected Services capability should be compatible, with specific enhanced support for:
- Mazda 3
- Mazda CX-30
- Mazda CX-5
- Other connected Mazda vehicles (basic support)

## Installation

### With HACS (Recommended)

1. Add `https://github.com/snake2715/home-assistant-mazda` as a custom repository in HACS
2. Search for "Mazda Connected Services" in HACS and install it
3. Restart Home Assistant

### Manual Installation

1. Copy the `mazda_cs` directory from `custom_components` in this repository
2. Place it inside your Home Assistant Core installation's `custom_components` directory
3. Restart Home Assistant

## Configuration

The integration can be configured via the Home Assistant UI:

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Mazda Connected Services" and select it
3. Enter your Mazda Connected Services email and password
4. Select your region (North America, Europe, or Japan)
5. Configure update intervals and other settings


## Available Services

- `mazda_cs.lock_doors`: Lock vehicle doors
- `mazda_cs.unlock_doors`: Unlock vehicle doors
- `mazda_cs.engine_start`: Remotely start engine
- `mazda_cs.engine_stop`: Stop engine
- `mazda_cs.send_poi`: Send point of interest to vehicle
- `mazda_cs.check_command_status`: Check status of previously issued commands

## Troubleshooting

If you experience issues with the integration:
1. Check that your Mazda Connected Services account credentials are correct
2. Verify that your vehicle is compatible with Connected Services
3. Check your vehicle's cellular connection
4. Enable debug mode in configuration options for detailed logging

## Contributing

Contributions to improve this integration are welcome. Please feel free to submit pull requests or report issues on our [GitHub repository](https://github.com/snake2715/home-assistant-mazda).

## Version Control & Updates

### Version Scheme
This integration follows semantic versioning (MAJOR.MINOR.PATCH):
- MAJOR version for incompatible API changes
- MINOR version for new functionality in a backward compatible manner
- PATCH version for backward compatible bug fixes

### Changelog
A detailed changelog is available in the [CHANGELOG.md](./CHANGELOG.md) file.

### Release Branches
- `main` - Stable release branch, recommended for most users
- `develop` - Development branch with newest features (may be unstable)

### Updates
Users are recommended to periodically check for updates:
1. In HACS: Go to HACS → Integrations → Mazda Connected Services → Update
2. For manual installations: Pull the latest changes from this repository

## License

This project is licensed under the Apache 2.0 License - see the LICENSE file for details.
