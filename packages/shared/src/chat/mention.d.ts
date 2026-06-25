export interface MentionNodeAttrs {
  /**
   * The identifier for the selected item that was mentioned, stored as a `data-id`
   * attribute.
   */
  id: string | null
  /**
   * The label to be rendered by the editor as the displayed text for this mentioned
   * item, if provided. Stored as a `data-label` attribute. See `renderLabel`.
   */
  label?: string | null
  /**
   * The inline representation of the mention when rendered in text format
   */
  renderInlineAs?: string | null
  /**
   * The type of the item that was mentioned, stored as a `data-item-type` attribute.
   */
  itemType?: string
  /**
   * The query to be used to fetch the item that was mentioned, stored as a `data-query` attribute.
   */
  query?: string
}
