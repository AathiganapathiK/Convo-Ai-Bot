import { Modal as staticModal } from 'antd';

let activeModal = staticModal;

export const setGlobalModal = (instance) => {
  if (instance) {
    activeModal = instance;
  }
};

export const modal = {
  confirm: (config) => activeModal.confirm(config),
  info: (config) => activeModal.info(config),
  success: (config) => activeModal.success(config),
  error: (config) => activeModal.error(config),
  warning: (config) => activeModal.warning(config),
  destroyAll: () => activeModal.destroyAll && activeModal.destroyAll(),
};

export default modal;
