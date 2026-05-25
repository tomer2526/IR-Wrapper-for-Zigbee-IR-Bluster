# Z2M IR Bridge

Home Assistant custom integration that exposes Zigbee2MQTT and ZHA IR emitters, such as ZS06, UFO-R11, and similar Zigbee IR blasters, as Home Assistant infrared entities.

## Installation with HACS

1. In Home Assistant, open HACS.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add this repository URL:

   ```text
   https://github.com/tomer2526/IR-Wrapper-for-Zigbee-IR-Bluster
   ```

4. Select **Integration** as the category.
5. Download **Z2M IR Bridge**.
6. Restart Home Assistant.
7. Go to **Settings** -> **Devices & services** -> **Add integration** and search for **Z2M IR Bridge**.

## Zigbee2MQTT

- Home Assistant with the MQTT integration configured.
- Zigbee2MQTT publishing device data under the configured base topic, usually `zigbee2mqtt`.

## ZHA

ZHA support expects the Tuya/Zosung IR device to expose the `ZosungIRControl` cluster. Many devices need a ZHA custom quirk before the send command is available.

For ZHA, add the device manually in the integration options using this format:

```text
Name|IEEE|endpoint_id|cluster_id|command
```

For most ZS06/Tuya IR devices with the Zosung quirk, the defaults are:

```text
Guest Room IR|f8:44:77:ff:fe:5a:57:3d|1|57348|2
```

You can also call the raw service directly:

```yaml
action: z2m_ir_bridge.send_code
data:
  backend: zha
  zha_ieee: f8:44:77:ff:fe:5a:57:3d
  zha_endpoint_id: 1
  zha_cluster_id: 57348
  zha_command: 2
  code: "CAUj4xEQAmwCEOAAAcALQAfAAwHSBuAZA0ArQCdAB8ADQA9AAUAPQAvAB0ALC9IGEAJsAhAC0gYQAg=="
```

## Notes

The integration listens to Zigbee2MQTT bridge device payloads and MQTT discovery topics, detects IR-capable devices by known model or exposed IR properties, and publishes IR send commands back to Zigbee2MQTT. ZHA devices are configured manually and send through `zha.issue_zigbee_cluster_command`.
