# Changelog

All notable changes to the Mazda Connected Services integration will be documented in this file.

## [1.1.1] - 2025-02-27

### Added
- Command status tracking with `visitNo` identifiers
- New `get_command_status` method to verify command completion
- Enhanced command logging for troubleshooting
- Added documentation about command reliability issues

### Fixed
- Improved reliability tracking for vehicle commands
- Better error detection for failed commands
- Added missing return values in several command methods

## [1.1.0] - 2025-02-27

### Added
- New configuration options:
  - Debug Mode: Enable detailed logging for troubleshooting
  - Log API Responses: Log all API responses (with privacy warning)
  - Testing Mode: Simulate API responses for testing
  - Performance Metrics: Track API call performance metrics
- Performance tracking for API calls
- Detailed logging for API interactions
- Configurable delays between API calls

### Changed
- Improved user interface for configuration:
  - Converted time intervals to more user-friendly units:
    - Status refresh interval from seconds to minutes (5-1440 min)
    - Health report interval from seconds to minutes (1-1440 min)
  - Added detailed descriptions for all configuration fields
  - Implemented proper conversion between user-friendly units and internal seconds
- Enhanced `strings.json` with more descriptive configuration options
- Improved error handling and logging
- Updated pymazda library with performance tracking and logging capabilities

### Fixed
- Various stability improvements
- Better error handling for API connectivity issues

## [1.0.0] - Initial Release

### Features
- Support for multiple Mazda vehicles
- Vehicle status reporting
- Vehicle health reports
- Vehicle commands (lock, unlock, engine start/stop, hazard lights)
- Configurable update intervals
