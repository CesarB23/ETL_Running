select activity_date, training_load, acute_7d, chronic_28d, acwr, is_reliable
from gold.fct_training_load
where activity_date >= current_date - interval 8 week
order by activity_date;
