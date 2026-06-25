declare namespace Api {
  namespace Message {
    interface MessageItem {
      id: string
      name: string
      createdAt: string
      isRead: boolean
      activity: Activity.ActivityItem
    }
  }
}
