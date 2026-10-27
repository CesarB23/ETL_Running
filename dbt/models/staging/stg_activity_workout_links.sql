select activity_id, planned_workout_id, garmin_workout_id, match_method
from {{ source('silver', 'activity_workout_links') }}
