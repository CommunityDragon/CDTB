# CommunityDragon ToolBox
## A library containing everything to build the file project

---

## Correlator
### Correlates Launcher Client patches with Game Client patches

### Dependencies:
pip install hachoir3

```python
from correlator import correlator

correlator.convert()  # gets all correlations
correlator.convert(['0.0.0.101', '0.0.0.30']) # gets specific correlations
```
