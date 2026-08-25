import { message as staticMessage } from 'antd';

let activeMessage = staticMessage;

export const setGlobalMessage = (instance) => {
  activeMessage = instance;
};

export const message = {
  success: (...args) => activeMessage.success(...args),
  error: (...args) => activeMessage.error(...args),
  warning: (...args) => activeMessage.warning(...args),
  info: (...args) => activeMessage.info(...args),
  loading: (...args) => activeMessage.loading(...args),
  destroy: (...args) => activeMessage.destroy(...args),
};
