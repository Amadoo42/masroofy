from .models import Notification

def notification_processor(request):
    if request.user.is_authenticated:
        unread_notifications = Notification.objects.filter(user=request.user, is_read=False)
        return {'unread_notifications': unread_notifications}
    return {'unread_notifications': []}