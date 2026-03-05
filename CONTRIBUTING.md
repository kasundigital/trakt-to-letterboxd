# Contributing

Thanks for your interest in contributing!

## Reporting bugs

Open an issue with:
- What you expected to happen
- What actually happened
- Your OS, Python version, and any error messages

## Pull requests

1. Fork the repo and create a branch: `git checkout -b my-feature`
2. Make your changes
3. Test locally with `./run.sh`
4. Open a PR with a clear description of the change

## Development setup

```bash
git clone https://github.com/YOUR_USERNAME/trakt-to-letterboxd
cd trakt-to-letterboxd
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/playwright install chromium
PORT=8888 venv/bin/python app.py
```

## Areas that need help

- Unit tests
- Windows support / testing
- Better Letterboxd error handling
- CSV chunking for libraries > 1,900 films
- i18n / translations
