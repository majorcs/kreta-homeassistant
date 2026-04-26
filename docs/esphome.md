# ESPHome processing for the Kréta JSON sensors

The Kréta integration exposes two sensors suitable for ESPHome devices:

| Sensor | Entity suffix | State | Attribute | Size | Default |
|--------|--------------|-------|-----------|------|---------|
| **Compact Timetable JSON** | `_compact_timetable_json` | Number of school days (int) | `compact_events_json` | ~4 KB | Enabled |
| **Timetable JSON** | `_timetable_json` | Last refresh ISO timestamp | `events_json` | ~16 KB | Disabled |

**Recommendation:** use the **Compact Timetable JSON** sensor for ESP32/ESP8266 devices. It is enabled by default, stays well within the HA recorder's 16 KB attribute limit, and its smaller payload fits comfortably in an ESP32's heap.

---

## Compact Timetable JSON sensor

### Payload structure

The `compact_events_json` attribute contains a JSON object with this structure:

```json
{
  "student": { "student_name": "Kis Tamás", "school_name": "..." },
  "days": {
    "2026-04-21": [
      { "start": "07:55", "end": "08:40", "summary": "Irodalom",      "idx": 1, "exam": false },
      { "start": "08:50", "end": "09:35", "summary": "Matematika",    "idx": 2, "exam": true  },
      { "start": "09:45", "end": "10:30", "summary": "Testnevelés",   "idx": 3, "exam": false }
    ],
    "2026-04-22": [ ... ]
  },
  "generated_at": "2026-04-21T06:00:00+00:00",
  "range_start": "2026-04-21",
  "range_end": "2026-05-04",
  "counts": { "lessons": 51, "tests": 3, "events": 51 }
}
```

Each entry in a day's list contains:

| Field | Type | Description |
|-------|------|-------------|
| `start` | `HH:MM` | Lesson start time |
| `end` | `HH:MM` | Lesson end time |
| `summary` | string | Subject name |
| `idx` | int | Lesson period index within the day |
| `exam` | bool | `true` if an announced test is scheduled for this lesson |

### Importing the attribute

```yaml
time:
  - platform: homeassistant
    id: homeassistant_time

text_sensor:
  - platform: homeassistant
    id: kreta_compact_json
    entity_id: sensor.student_one_compact_timetable_json
    attribute: compact_events_json
    internal: true
    on_value:
      then:
        - lambda: |-
            ESP_LOGI("kreta", "Compact JSON received: %u bytes", x.size());
```

Replace `sensor.student_one_compact_timetable_json` with your actual entity ID.  
The `time` component is required for the "today's lessons" examples below.

---

### Example: display today's lessons on the serial log

This example parses the compact payload and logs every lesson for today.

```yaml
globals:
  - id: todays_lessons
    type: std::string
    restore_value: no
    initial_value: '""'

time:
  - platform: homeassistant
    id: homeassistant_time

text_sensor:
  - platform: homeassistant
    id: kreta_compact_json
    entity_id: sensor.student_one_compact_timetable_json
    attribute: compact_events_json
    internal: true
    on_value:
      then:
        - lambda: |-
            DynamicJsonDocument doc(6144);
            if (deserializeJson(doc, x.c_str())) return;

            // Build today's date key: "YYYY-MM-DD"
            auto now = id(homeassistant_time).now();
            if (!now.is_valid()) return;
            char today[11];
            snprintf(today, sizeof(today), "%04d-%02d-%02d",
                     now.year, now.month, now.day_of_month);

            JsonArray lessons = doc["days"][today].as<JsonArray>();
            if (lessons.isNull() || lessons.size() == 0) {
              ESP_LOGI("kreta", "No lessons today (%s)", today);
              id(todays_lessons) = "No lessons today";
              return;
            }

            std::string result;
            for (JsonObject lesson : lessons) {
              const char *start   = lesson["start"]   | "?";
              const char *end     = lesson["end"]     | "?";
              const char *summary = lesson["summary"] | "?";
              bool exam           = lesson["exam"]    | false;

              char line[64];
              snprintf(line, sizeof(line), "%s-%s  %s%s",
                       start, end, summary, exam ? " [!]" : "");
              ESP_LOGI("kreta", "%s", line);
              if (!result.empty()) result += '\n';
              result += line;
            }
            id(todays_lessons) = result;
```

---

### Example: find the next upcoming lesson today

Compares the current time against each lesson's start time and stores the first lesson that has not yet ended.

```yaml
globals:
  - id: next_lesson_summary
    type: std::string
    restore_value: no
    initial_value: '""'
  - id: next_lesson_start
    type: std::string
    restore_value: no
    initial_value: '""'
  - id: next_lesson_has_exam
    type: bool
    restore_value: no
    initial_value: "false"

time:
  - platform: homeassistant
    id: homeassistant_time

text_sensor:
  - platform: template
    name: "Next lesson"
    lambda: |-
      if (id(next_lesson_summary).empty()) return {"No more lessons today"};
      std::string label = id(next_lesson_start) + "  " + id(next_lesson_summary);
      if (id(next_lesson_has_exam)) label += " [exam]";
      return {label};

  - platform: homeassistant
    id: kreta_compact_json
    entity_id: sensor.student_one_compact_timetable_json
    attribute: compact_events_json
    internal: true
    on_value:
      then:
        - lambda: |-
            DynamicJsonDocument doc(6144);
            if (deserializeJson(doc, x.c_str())) return;

            auto now = id(homeassistant_time).now();
            if (!now.is_valid()) return;

            // Today's date key
            char today[11];
            snprintf(today, sizeof(today), "%04d-%02d-%02d",
                     now.year, now.month, now.day_of_month);
            // Current time as "HH:MM" for string comparison
            char current_time[6];
            snprintf(current_time, sizeof(current_time), "%02d:%02d",
                     now.hour, now.minute);

            JsonArray lessons = doc["days"][today].as<JsonArray>();
            id(next_lesson_summary) = "";
            id(next_lesson_start)   = "";
            id(next_lesson_has_exam) = false;

            if (lessons.isNull()) return;

            for (JsonObject lesson : lessons) {
              const char *end = lesson["end"] | "00:00";
              // Skip lessons that have already ended
              if (strcmp(end, current_time) <= 0) continue;

              id(next_lesson_summary) = std::string(lesson["summary"] | "?");
              id(next_lesson_start)   = std::string(lesson["start"]   | "?");
              id(next_lesson_has_exam) = lesson["exam"] | false;
              break;
            }
```

---

### Example: count lessons and exams for today

Useful for a status line on an e-ink display.

```yaml
sensor:
  - platform: template
    name: "Lessons today"
    id: lessons_today_count
    accuracy_decimals: 0

  - platform: template
    name: "Exams today"
    id: exams_today_count
    accuracy_decimals: 0

text_sensor:
  - platform: homeassistant
    id: kreta_compact_json
    entity_id: sensor.student_one_compact_timetable_json
    attribute: compact_events_json
    internal: true
    on_value:
      then:
        - lambda: |-
            DynamicJsonDocument doc(6144);
            if (deserializeJson(doc, x.c_str())) return;

            auto now = id(homeassistant_time).now();
            if (!now.is_valid()) return;
            char today[11];
            snprintf(today, sizeof(today), "%04d-%02d-%02d",
                     now.year, now.month, now.day_of_month);

            JsonArray lessons = doc["days"][today].as<JsonArray>();
            if (lessons.isNull()) {
              id(lessons_today_count).publish_state(0);
              id(exams_today_count).publish_state(0);
              return;
            }

            int total = 0, exams = 0;
            for (JsonObject lesson : lessons) {
              total++;
              if (lesson["exam"] | false) exams++;
            }
            id(lessons_today_count).publish_state(total);
            id(exams_today_count).publish_state(exams);
```

---

### Example: render today's schedule on an e-ink display

Full example combining the above pieces into a display render function.  
Assumes a 2-colour 296×128 e-ink display (e.g. Waveshare 2.9″) connected via SPI.

```yaml
esphome:
  name: school-display
  libraries:
    - ArduinoJson

time:
  - platform: homeassistant
    id: homeassistant_time

globals:
  - id: compact_json_str
    type: std::string
    restore_value: no
    initial_value: '""'

text_sensor:
  - platform: homeassistant
    id: kreta_compact_json
    entity_id: sensor.student_one_compact_timetable_json
    attribute: compact_events_json
    internal: true
    on_value:
      then:
        - lambda: id(compact_json_str) = x;
        - component.update: eink_display

font:
  - file: "gfonts://Roboto"
    id: font_small
    size: 12
  - file: "gfonts://Roboto"
    id: font_bold
    size: 14
    weight: bold

display:
  - platform: waveshare_epaper
    id: eink_display
    # ... (cs_pin, dc_pin, busy_pin, reset_pin, model: 2.90in)
    lambda: |-
      it.fill(COLOR_OFF);

      if (id(compact_json_str).empty()) {
        it.print(4, 4, id(font_bold), "Waiting for data...");
        return;
      }

      DynamicJsonDocument doc(6144);
      if (deserializeJson(doc, id(compact_json_str).c_str())) {
        it.print(4, 4, id(font_bold), "JSON error");
        return;
      }

      auto now = id(homeassistant_time).now();
      if (!now.is_valid()) {
        it.print(4, 4, id(font_bold), "No time sync");
        return;
      }

      char today[11];
      snprintf(today, sizeof(today), "%04d-%02d-%02d",
               now.year, now.month, now.day_of_month);

      // Header: student name + date
      const char *student = doc["student"]["student_name"] | "Student";
      it.printf(4, 2, id(font_bold), "%s – %s", student, today);

      JsonArray lessons = doc["days"][today].as<JsonArray>();
      if (lessons.isNull() || lessons.size() == 0) {
        it.print(4, 22, id(font_small), "No lessons today");
        return;
      }

      // Current time for highlighting active lesson
      char current_time[6];
      snprintf(current_time, sizeof(current_time), "%02d:%02d",
               now.hour, now.minute);

      int y = 22;
      for (JsonObject lesson : lessons) {
        if (y > 112) break;  // display height guard

        const char *start   = lesson["start"]   | "?";
        const char *end     = lesson["end"]     | "?";
        const char *summary = lesson["summary"] | "?";
        bool exam           = lesson["exam"]    | false;
        int  idx            = lesson["idx"]     | 0;

        // Highlight the currently active lesson
        bool active = strcmp(start, current_time) <= 0 &&
                      strcmp(current_time, end) < 0;
        if (active) {
          it.filled_rectangle(0, y - 1, 296, 15, COLOR_ON);
        }

        auto color = active ? COLOR_OFF : COLOR_ON;
        char line[48];
        snprintf(line, sizeof(line), "%d. %s-%s  %s%s",
                 idx, start, end, summary, exam ? " !" : "");
        it.print(4, y, id(font_small), color, line);
        y += 16;
      }
```

---

## Full Timetable JSON sensor (legacy / advanced)

The original **Timetable JSON** sensor is **disabled by default** (its ~16 KB payload can trigger HA recorder warnings). Enable it in the HA UI if you need the extra fields it provides (`uid`, `description`, `location`, `subject_name`, `source`, full exam details).

### What to import from Home Assistant

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

### Minimal parsing example

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

### Useful fields in the full payload

- `student.student_name`
- `events[].summary`
- `events[].start` (ISO-8601 datetime)
- `events[].end` (ISO-8601 datetime)
- `events[].description`
- `events[].source` (`lesson`, `lesson_with_exam`, `exam_only`)
- `events[].exam` (full exam object or `null`)
- `events[].lesson_index`
- `events[].subject_name`

If an exam is merged into a lesson, `source` is `lesson_with_exam`. If an exam could not be matched to a lesson it appears as its own event with `source` set to `exam_only`.
