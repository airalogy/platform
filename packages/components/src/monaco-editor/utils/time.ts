export function isoDateStringFormat(isoDateString: string) {
  const date = new Date(isoDateString)

  let month: string | number = date.getMonth() + 1
  let day: string | number = date.getDate()

  month = month < 10 ? `0${month}` : month
  day = day < 10 ? `0${day}` : day

  return `${month}月${day}日`
}
