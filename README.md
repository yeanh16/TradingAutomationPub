TradingAutomationPub is a Python trading automation toolkit for running crypto derivatives strategies across Binance, Bybit, Gate.io, Phemex, and more. It wraps exchange REST/WebSocket APIs in reusable clients, used for running and trading autonomously.

Features:
Discord integration for alerts to be sent directly to the Discord app on mobile
Twitter/X news and tweets data stream for monitoring current events that could impact the cryptocurrency markets
SQL database for logging trades made

### Quick Start
```bash
# 1. Install dependencies
pip install .

# 2. Run the main trading application
bash scripts/run

# 3. Monitor with health check
bash scripts/check
```

### Running Individual Components
```bash
# Main aggregated futures trading
python -m trading_automation.apps.AggFuturesMain

# Individual futures trading with parameters
python -m trading_automation.apps.FuturesMain [parameters]

# Data download
python -m src.data.DownloadKlines

# Analysis tools
python -m src.analysis.TradesAnalyser
```

## Development

### Adding New Features
- **New exchange client**: Add to `src/trading_automation/clients/`
- **New trading strategy**: Add to `src/trading_automation/bots/`
- **New analysis tool**: Add to `src/trading_automation/analysis/`
- **WebSocket feeds**: Add to `src/trading_automation/websockets/`

### Testing
```bash
# Run tests
python -m pytest tests/

# Verify structure
python verify_structure.py
```

## Configuration Files

- **requirements.txt**: Python dependencies
- **args_reference.txt**: Trading argument reference
- **capital_instruments.txt**: Capital.com instrument list
- **config/**: Setup and configuration scripts

## Troubleshooting

### Import Errors
If you encounter import errors, ensure:
1. Python path includes `src/` directory
2. All dependencies are installed

### Missing Dependencies
```bash
pip install .
```

## Directory Structure

```
TradingAutomation/
├── src/                    # Main source code
│   ├── trading_automation/
│   │   ├── apps/              # Main applications and entry points
│   │   │   ├── AggFuturesMain.py      # Aggregated futures trading main app
│   │   │   ├── FuturesMain.py         # Individual futures trading app
│   │   │   └── FuturesManager.py      # Futures management logic
│   │   ├── clients/           # Exchange client implementations
│   │   ├── UniversalClient.py     # Universal client for multiple exchanges
│   │   ├── BingxClient.py         # BingX exchange client
│   │   ├── BybitClient.py         # Bybit exchange client
│   │   ├── CapitalClient.py       # Capital.com client
│   │   ├── DiscordClient.py       # Discord integration client
│   │   └── ... (other exchange clients)
│   │   ├── websockets/        # WebSocket managers for real-time data
│   │   ├── PhemexWebSocketMaster.py
│   │   ├── BybitWebSocketManager.py
│   │   └── ... (other websocket managers)
│   │   ├── core/              # Core utilities and shared functionality
│   │   ├── Utils.py               # Utility functions
│   │   ├── Logger.py              # Logging functionality
│   │   ├── WebsocketInterface.py  # WebSocket interface
│   │   └── UniversalClientWebsocket.py
│   │   ├── data/              # Data download and processing
│   │   ├── DownloadKlines.py
│   │   └── DownloadKlinesOneTime.py
│   │   ├── bots/              # Trading bots
│   │   └── CounterTrendStocksBot.py
│   │   └── analysis/          # Analysis and processing tools
│       ├── TradesAnalyser.py
│       ├── ProcessTradesText.py
│       └── TwitterStream.py
├── tests/                 # Test files
│   ├── ArbitrageTest.py
│   ├── OrderBookTest.py
│   └── UtilsTest.py
├── config/                # Configuration files and setup
│   ├── ServerTimeCheck.py
│   └── SetUpSQLtables.py
├── scripts/               # Utility scripts
│   ├── run                # Main run script
│   ├── check              # Health check script
│   ├── ChangeAllArgFiles.py
│   └── sim.py
├── third_party/           # External libraries
│   ├── ibapi/             # Interactive Brokers API
│   └── ibTestbed/         # IB testing framework
└── docs/                  # Documentation (to be added)
```

## Running the Application

### Setup
1. Ensure Python 3.12+ is installed
2. Install dependencies: `pip install .`
3. Use the provided CLI entry points (e.g. `trading-futures`)

### Main Applications
- **Aggregated Futures Trading**: `bash scripts/run`
- **Individual Futures Trading**: `python -m trading_automation.apps.FuturesMain [args]`

### Health Monitoring
- **Health Check**: `bash scripts/check`

## Import Structure

The new structure exposes modules via the `trading_automation` package. Import modules directly, for example:

```python
from trading_automation.clients.UniversalClient import UniversalClient
from trading_automation.core.Utils import round_interval_nearest
```

