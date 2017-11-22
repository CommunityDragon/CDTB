# CommunityDragon ToolBox
## A library containing everything to build the files for DragonBuilder

---

## Correlator
#### Description
Correlates Launcher Client patches with Game Client patches

#### Dependencies:
pip install hachoir3

#### Example
```python
from correlator import Correlator

c = Correlator()

c.convert()  # gets all correlations
c.convert(['0.0.0.101', '0.0.0.30']) # gets specific correlations
```
