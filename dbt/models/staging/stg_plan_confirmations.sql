select planned_workout_id, activity_id, plan_hash, confirmed_at
from {{ source('silver', 'plan_confirmations') }}
