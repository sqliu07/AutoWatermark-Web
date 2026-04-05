import { createI18n } from 'vue-i18n'
import zh from './zh'
import en from './en'

const savedLang = localStorage.getItem('lang') || 'zh'

export const i18n = createI18n({
  legacy: false,
  locale: savedLang,
  fallbackLocale: 'zh',
  messages: { zh, en },
})

export function setLanguage(lang) {
  i18n.global.locale.value = lang
  localStorage.setItem('lang', lang)
  document.documentElement.lang = lang
}
