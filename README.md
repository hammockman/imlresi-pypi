# imlresi
Tools for dealing with [IML-Resi PowerDrill](https://www.iml-service.com/product/iml-powerdrill/) data using python.

**THIS PACKAGE IS UNOFFICAL AND HAS BEEN DEVELOPED INDEPENDENT OF IML**

Current limitations:

1. Focus is on actual measurements made by the tool rather than meta-info.
1. Poor support for data generated in PD-Tools (e.g. "assessments").


## Install

https://pypi.org/project/imlresi/

```sh
pip install imlresi
```



## Use


```python
from imlresi.trace import Trace

tr = Trace()
tr.read('trace.rgp')
tr.to_json()
```