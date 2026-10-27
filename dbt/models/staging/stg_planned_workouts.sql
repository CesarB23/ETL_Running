select planned_workout_id, week_start, scheduled_date, title,
       plan_hash, garmin_workout_id, garmin_workout_name
from {{ source('silver', 'planned_workouts') }}
