# ESPHome processing for the Kreta JSON sensor

The Kreta integration exposes a sensor named **Timetable JSON**. Its **state** is only the last refresh timestamp, while the full structured payload is available in the **`events_json` attribute**.

That means an ESPHome device should read the **attribute**, not the sensor state.

## What to import from Home Assistant

Use a `text_sensor` with:

- `entity_id`: the Home Assistant entity of the Kreta JSON sensor
- `attribute: events_json`

Example:

```yaml
text_sensor:
  - platform: homeassistant
    id: kreta_events_json
    entity_id: sensor.student_one_timetable_json
    attribute: events_json
    internal: true
    on_value:
      then:
        - lambda: |-
            ESP_LOGI("kreta", "Received Kreta JSON payload: %u bytes", x.size());
```

Replace `sensor.student_one_timetable_json` with the actual entity ID from your Home Assistant instance.

## Minimal parsing example

The payload contains a top-level `student` object and an `events` array. A simple ESPHome lambda can parse it and extract the next event:

```yaml
globals:
  - id: next_lesson_name
    type: std::string
    restore_value: no
    initial_value: '""'

text_sensor:
  - platform: template
    name: "Next Kreta lesson"
    lambda: |-
      return id(next_lesson_name);

  - platform: homeassistant
    id: kreta_events_json
    entity_id: sensor.student_one_timetable_json
    attribute: events_json
    internal: true
    on_value:
      then:
        - lambda: |-
            DynamicJsonDocument doc(16384);
            auto error = deserializeJson(doc, x.c_str());
            if (error) {
              ESP_LOGE("kreta", "JSON parse failed: %s", error.c_str());
              return;
            }

            JsonArray events = doc["events"].as<JsonArray>();
            if (events.isNull() || events.size() == 0) {
              id(next_lesson_name) = "No upcoming lesson";
              return;
            }

            JsonObject first_event = events[0];
            const char *summary = first_event["summary"] | "Unknown lesson";
            id(next_lesson_name) = summary;
```

## Useful fields in the payload

The most useful fields for ESPHome displays and automations are usually:

- `student.student_name`
- `events[].summary`
- `events[].start`
- `events[].end`
- `events[].description`
- `events[].source`
- `events[].exam`

If an exam is merged into a lesson, `source` is typically `lesson_with_exam`. If an exam could not be matched to a lesson, it appears as its own event with `source` set to `exam_only`.

## Practical recommendation

For small ESPHome devices, it is usually best to:

1. import the `events_json` attribute
2. parse only the fields you actually need
3. store the extracted values in `globals`, template sensors, or display widgets

This keeps memory usage lower than trying to work with the whole JSON payload repeatedly.
