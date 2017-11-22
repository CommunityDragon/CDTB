# ClientCorrelator
## Correlate launcher client patches with game client patches

### Dependencies:
pip install hachoir3

```python
from clientcorrelator import clientcorrelator

clientcorrelator.get_correlations()  # gets the correlations in dict format
```