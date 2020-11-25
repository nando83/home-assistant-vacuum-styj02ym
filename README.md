# Hacky Home assistant support for Xiaomi vacuum STYJ02YM 

<<<<<<< HEAD
## Install with HACS

Latest [HACS](https://hacs.xyz/) require HA 0.110.0 or newer:

![](demo_hacs1.gif)

Old HACS:

![](demo_hacs.gif)

## Manual Install:
=======
### Install whit HACS:

### Manual Install:
>>>>>>> 9cde8c7cacc7f052a380d3bf8a24910623ea4775
- Create the following folder structure: /config/custom_components/miio2 and place all files there [4 files](https://github.com/nqkdev/home-assistant-vacuum-styj02ym) there.
- Add the configuration to configuration.yaml, example:

```yaml
vacuum:
  - platform: miio2
    host: 192.168.68.105
    token: !secret vacuum
    name: Mi hihi
```
