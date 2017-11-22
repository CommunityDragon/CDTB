# ClientCorrelator
## Correlate launcher client patches with game client patches

### Dependencies:
pip install hachoir3

### How to use:
Run the file `extract_client_metadata.py` to download all of the League clients. The metadata will be extrafted from them, and the client release numbers -> patch numbers will be correlated.

Results are saved in the file `version_conversion.json`.
