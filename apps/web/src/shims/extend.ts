type Extendable = Record<PropertyKey, any>

const hasOwn = Object.prototype.hasOwnProperty
const toString = Object.prototype.toString

function isPlainObject(value: unknown): value is Extendable {
  if (!value || toString.call(value) !== "[object Object]") {
    return false
  }

  const object = value as Extendable
  const hasOwnConstructor = hasOwn.call(object, "constructor")
  const constructor = object.constructor as { prototype?: object } | undefined
  const hasIsPrototypeOf = constructor?.prototype && hasOwn.call(constructor.prototype, "isPrototypeOf")

  if (constructor && !hasOwnConstructor && !hasIsPrototypeOf) {
    return false
  }

  const key = Object.keys(object)[0]

  return key === undefined || hasOwn.call(object, key)
}

function getProperty(object: Extendable, name: PropertyKey) {
  if (name === "__proto__" && !hasOwn.call(object, name)) {
    return undefined
  }

  return object[name]
}

function setProperty(target: Extendable, name: PropertyKey, value: unknown) {
  if (name === "__proto__") {
    Object.defineProperty(target, name, {
      configurable: true,
      enumerable: true,
      value,
      writable: true,
    })
    return
  }

  target[name] = value
}

export default function extend(...args: any[]) {
  let target = args[0]
  let index = 1
  const deep = typeof target === "boolean" ? target : false

  if (deep) {
    target = args[1] || {}
    index = 2
  }

  if (target == null || (typeof target !== "object" && typeof target !== "function")) {
    target = {}
  }

  for (; index < args.length; index++) {
    const options = args[index]

    if (options == null) {
      continue
    }

    for (const name in options) {
      const source = getProperty(target, name)
      const copy = getProperty(options, name)

      if (target === copy) {
        continue
      }

      if (deep && copy && (isPlainObject(copy) || Array.isArray(copy))) {
        const clone = Array.isArray(copy)
          ? (Array.isArray(source) ? source : [])
          : (isPlainObject(source) ? source : {})

        setProperty(target, name, extend(deep, clone, copy))
      }
      else if (copy !== undefined) {
        setProperty(target, name, copy)
      }
    }
  }

  return target
}
