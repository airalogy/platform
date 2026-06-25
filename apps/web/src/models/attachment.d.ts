declare namespace Api {
  namespace Attachment {
    interface AttachmentItemResponse {
      id: string
      filename: string
      url: string
    }
    interface AttachmentItem {
      id: string
      filename: string
      url: string
      airalogy_file_id: string
    }
  }
}
