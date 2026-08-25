import React, {
  useEffect,
  useState
} from "react";

import {
  Modal,
  Form,
  Input,
  Button
} from "antd";
import { message } from "../utils/message";

import {
  getCompanyInfo,
  getTenantConfig,
  updateTenantConfig
} from "../services/configService";

function PlatformSettingsModal({
  open,
  onClose,
  token
}) {

  const [form] = Form.useForm();

  const [loading,
    setLoading] =
    useState(false);

  useEffect(() => {

    if (open) {

      loadData();

    }

  }, [open]);

  const loadData = async () => {

    try {

      const company =
        await getCompanyInfo(
          token
        );

      const config =
        await getTenantConfig(
          token
        );

      form.setFieldsValue({
        company_name:
          company.company_name,

        company_code:
          company.company_code,

        timezone:
          config.timezone,

        currency:
          config.currency,

        date_format:
          config.date_format,

        sql_dialect:
          config.sql_dialect
      });

    } catch {

      message.error(
        "Failed to load configuration"
      );

    }

  };

  const saveConfig =
    async (values) => {

      setLoading(true);

      try {

        await updateTenantConfig(
          token,
          values
        );

        message.success(
          "Configuration updated"
        );

        onClose();

      } catch {

        message.error(
          "Update failed"
        );

      }

      setLoading(false);

    };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={700}
      title="Platform Settings"
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={saveConfig}
      >
        <Form.Item
          label="Company Name"
          name="company_name"
        >
          <Input disabled />
        </Form.Item>

        <Form.Item
          label="Company Code"
          name="company_code"
        >
          <Input disabled />
        </Form.Item>

        <Form.Item
          label="Timezone"
          name="timezone"
        >
          <Input />
        </Form.Item>

        <Form.Item
          label="Currency"
          name="currency"
        >
          <Input />
        </Form.Item>

        <Form.Item
          label="Date Format"
          name="date_format"
        >
          <Input />
        </Form.Item>

        <Form.Item
          label="SQL Dialect"
          name="sql_dialect"
        >
          <Input />
        </Form.Item>

        <Button
          type="primary"
          htmlType="submit"
          loading={loading}
        >
          Save Configuration
        </Button>
      </Form>
    </Modal>
  );
}

export default PlatformSettingsModal;