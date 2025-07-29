from datetime import datetime
from datetime import timezone

LOCAL_TZ = timezone(datetime.now().astimezone().utcoffset())
