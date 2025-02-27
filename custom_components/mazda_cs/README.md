# Mazda Connected Services Integration for Home Assistant

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]
[![Community Forum][forum-shield]][forum]

![Mazda Connected Services Logo](https://raw.githubusercontent.com/bdr99/pymazda/master/images/mazda-logo.png)

> Monitor and control your Mazda vehicles in Home Assistant

This custom integration allows you to connect your Mazda vehicles to Home Assistant through the Mazda Connected Services API. Monitor vehicle status, receive health reports, and control various vehicle functions directly from your Home Assistant dashboard.

## Features

- **Multi-Vehicle Support**: Connect and manage multiple Mazda vehicles with a single account
- **Comprehensive Vehicle Status**: Monitor key information including:
  - Fuel level and remaining range
  - Odometer reading
  - Door, window, and trunk status
  - Engine and interior temperature
  - Last updated location
  - Tire pressure readings
- **Detailed Health Reports**: Access vehicle health information including:
  - Oil status and life remaining
  - Battery health
  - Warning light status
  - Scheduled maintenance information
- **Vehicle Commands**: Control your vehicle remotely:
  - Lock/unlock doors
  - Start/stop engine (where supported)
  - Activate hazard lights for vehicle location
- **Configurable Update Intervals**: Set custom refresh intervals for status and health reports
- **Advanced Debugging Options**: Troubleshooting tools for developers and power users

## Screenshots

*Screenshots of the integration in Home Assistant would be placed here.*

## Requirements

- Home Assistant (Core 2021.12.0 or newer)
- Mazda Connected Services account with connected vehicle(s)
- Vehicle(s) with Connected Services subscription

## Installation

### Option 1: HACS Installation (Recommended)

1. Ensure that [HACS](https://hacs.xyz/) is installed in your Home Assistant instance
2. Go to HACS → Integrations → "⋮" menu → Custom repositories
3. Add the URL of this repository with category "Integration"
4. Click "ADD"
5. Search for "Mazda Connected Services" in HACS and install it
6. Restart Home Assistant

### Option 2: Manual Installation

1. Download the latest release of this integration
2. Extract the contents
3. Copy the `custom_components/mazda_cs` directory to your Home Assistant `custom_components` directory
4. Restart Home Assistant

## Configuration

### Initial Setup

1. Go to **Configuration** → **Integrations** in the Home Assistant UI
2. Click on the "+" button to add a new integration
3. Search for "Mazda Connected Services" and select it
4. Enter your Mazda Connected Services account credentials:
   - Email address
   - Password
   - Region (North America, Europe, Japan)
5. Configure optional settings (or use the defaults)
6. Click "Submit" to complete the setup

### Configuration Options

All settings can be adjusted at any time by selecting "Configure" on the integration in the Home Assistant Integrations page.

#### Main Settings

| Setting | Description | Default |
|---------|-------------|---------|
| Email | Your Mazda Connected Services account email | Required |
| Password | Your Mazda Connected Services account password | Required |
| Region | Your region (North America, Europe, Japan) | Required |

#### Update Intervals

| Setting | Description | Range | Default |
|---------|-------------|-------|---------|
| Status Refresh Interval | How often to update vehicle status | 5-1440 minutes | 30 minutes |
| Health Report Interval | How often to request vehicle health reports | 0.1-24 hours | 12 hours |

#### Advanced Settings

| Setting | Description | Range | Default |
|---------|-------------|-------|---------|
| Vehicle Processing Delay | Delay between processing multiple vehicles | 0-10 seconds | 1 second |
| Endpoint Processing Delay | Delay between API calls | 0-10 seconds | 1 second |

#### Debugging Options

| Setting | Description | Default |
|---------|-------------|---------|
| Debug Mode | Enable detailed logging for troubleshooting | Disabled |
| Log API Responses | Log all API responses (warning: may include sensitive information) | Disabled |
| Testing Mode | Simulate API responses for testing | Disabled |
| Performance Metrics | Track API call performance metrics | Disabled |

## Available Entities

The integration creates several entities for each vehicle:

### Sensors

| Entity | Description | Attributes |
|--------|-------------|------------|
| `sensor.vehicle_name_status` | Current vehicle status information | fuel_level, fuel_distance_remaining, odometer, doors_locked, windows_closed, trunk_open, interior_temperature, exterior_temperature, location, last_updated |
| `sensor.vehicle_name_health` | Vehicle health information | oil_life_remaining, battery_health, warning_lights, maintenance_due, tire_pressure, last_updated |

### Services

The following services are available for controlling your vehicle(s):

| Service | Description | Parameters |
|---------|-------------|------------|
| `mazda_cs.lock_doors` | Lock vehicle doors | device_id |
| `mazda_cs.unlock_doors` | Unlock vehicle doors | device_id |
| `mazda_cs.start_engine` | Start vehicle engine | device_id, runtime (optional) |
| `mazda_cs.stop_engine` | Stop vehicle engine | device_id |
| `mazda_cs.hazard_lights` | Activate hazard lights | device_id |
| `mazda_cs.send_poi` | Send a point of interest to vehicle navigation | device_id, latitude, longitude, poi_name |
| `mazda_cs.check_command_status` | Check the status of a command | device_id, visit_no |

The `check_command_status` service deserves special attention. It allows you to verify if a command actually completed successfully on the vehicle (not just the API). When you execute a command, look for the `visitNo` in the Home Assistant logs (with Debug Mode enabled) and use this as the parameter for the status check.

**Example service call to check command status:**
```yaml
service: mazda_cs.check_command_status
data:
  device_id: your_device_id
  visit_no: "GW02250227075002503649"  # The visitNo from the original command response
```

## Automations

Here are some example automations you can create with this integration:

### Automatically Lock Doors When Away

```yaml
automation:
  - alias: "Lock Mazda when leaving home"
    trigger:
      - platform: zone
        entity_id: device_tracker.phone
        zone: zone.home
        event: leave
    action:
      - service: mazda_cs.lock_doors
        data:
          device_id: your_device_id
```

### Start Engine on Cold Mornings

```yaml
automation:
  - alias: "Start Mazda on cold mornings"
    trigger:
      - platform: time
        at: "07:30:00"
    condition:
      - condition: numeric_state
        entity_id: weather.home
        attribute: temperature
        below: 5
    action:
      - service: mazda_cs.start_engine
        data:
          device_id: your_device_id
          runtime: 10
```

## Troubleshooting

If you encounter issues with the integration:

### Connection Problems

1. Verify your Mazda account credentials are correct
2. Check that your vehicle(s) have an active Connected Services subscription
3. Ensure your vehicle is in an area with cellular coverage
4. Try refreshing your connection by removing and re-adding the integration

### Command Reliability Issues

The Mazda Connected Services API has a known issue where commands (like lock/unlock) may report success in the API response but fail to complete on the vehicle. This can happen due to:

- Poor cellular connectivity to the vehicle
- Vehicle being in a deep sleep state
- Server-side issues with the Mazda Connected Services platform

When this happens, Home Assistant may show a successful command (green status) while the Mazda app shows a failed command.

**What we've done to help:**
1. Added detailed command tracking with `visitNo` identifiers
2. Implemented command status verification via the `get_command_status` method
3. Enhanced debugging to show command attempts and statuses

**To troubleshoot command failures:**
1. Enable Debug Mode in the integration settings
2. Check the Home Assistant logs for the command's `visitNo` identifier
3. Wait 1-2 minutes after sending a command before assuming it failed (commands can be delayed)
4. If commands consistently fail, try refreshing the vehicle status first, then sending the command again

### Data Not Updating

1. Check the status update interval in your configuration
2. Verify your vehicle has been used recently (some data only updates after vehicle use)
3. Check for API status issues on the Mazda Connected Services platform

### Debug Logging

For advanced troubleshooting:

1. Enable **Debug Mode** in the integration configuration
2. If requested by a developer, enable **Log API Responses** 
3. Check Home Assistant logs for detailed information:
   ```
   2025-02-27 01:20:45 DEBUG (MainThread) [custom_components.mazda_cs] Vehicle status update successful for Vehicle: CX-5
   ```

4. Look for errors such as:
   ```
   2025-02-27 01:20:45 ERROR (MainThread) [custom_components.mazda_cs] Failed to connect to Mazda API: Connection timeout
   ```

## Privacy Notice

When **Log API Responses** is enabled, detailed API response data will be written to your Home Assistant logs. This may include sensitive information about your vehicle including location history, VIN, and usage patterns. Only enable this option when necessary for troubleshooting and disable it when no longer needed.

## Contributing

Contributions to this integration are welcome! Here's how you can help:

1. Fork the repository
2. Create a feature branch: `git checkout -b my-new-feature`
3. Commit your changes: `git commit -am 'Add some feature'`
4. Push to the branch: `git push origin my-new-feature`
5. Submit a pull request

## FAQ

**Q: Which Mazda vehicles are supported?**  
A: Most Mazda vehicles from 2017 onwards with Connected Services capability are supported. Specific features vary by vehicle model and year.

**Q: Is my data secure?**  
A: This integration communicates directly with the official Mazda API using your credentials. No data is sent to third parties.

**Q: How frequent are the updates?**  
A: Status updates are configurable from 5 minutes to 24 hours. Note that very frequent updates may impact vehicle battery life as it wakes up the vehicle's cellular modem.

**Q: Why are some commands slow to execute?**  
A: Remote commands are sent through the Mazda Connected Services cellular network. Depending on your vehicle's location and cellular reception, commands may take 30-60 seconds to complete.

**Q: Will this drain my car battery?**  
A: The Connected Services system is designed to minimize battery drain, but very frequent status checks could potentially impact battery life. Use reasonable update intervals.

## API Details

This integration uses a modified version of the [pymazda](https://github.com/bdr99/pymazda) library to communicate with the Mazda Connected Services API. The library handles authentication, API requests, and parsing of the response data.

The integration respects API rate limits by implementing configurable delays between requests to prevent account lockouts.

## Credits

This integration uses a modified version of the [pymazda](https://github.com/bdr99/pymazda) library created by [bdr99](https://github.com/bdr99).

## License

This project is licensed under the MIT License - see the LICENSE file for details.

---

[commits-shield]: https://img.shields.io/github/commit-activity/y/username/ha-mazda-cs.svg
[commits]: https://github.com/username/ha-mazda-cs/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/username/ha-mazda-cs.svg
[releases-shield]: https://img.shields.io/github/release/username/ha-mazda-cs.svg
[releases]: https://github.com/username/ha-mazda-cs/releases
