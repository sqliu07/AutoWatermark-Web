import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  Button,
  ConfigProvider,
  Modal,
  Progress,
  Segmented,
  Spin,
  Switch,
  Tag,
} from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import { i18n } from './i18n'
import App from './App.vue'
import './styles/global.css'

const app = createApp(App)
app.use(createPinia())
app.use(i18n)
app.use(Button)
app.use(ConfigProvider)
app.use(Modal)
app.use(Progress)
app.use(Segmented)
app.use(Spin)
app.use(Switch)
app.use(Tag)
app.mount('#app')
