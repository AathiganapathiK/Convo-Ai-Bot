import React from 'react';
import {
  Modal,
  Card,
  Descriptions,
  List,
  Badge,
  Alert,
  Input,
  Button,
  Typography,
  Space,
} from 'antd';
import { CheckOutlined, SafetyCertificateOutlined } from '@ant-design/icons';

const { Text, Title } = Typography;

const DeleteDatasourceModal = ({
  open,
  loading,
  deleteSummary,
  confirmText,
  setConfirmText,
  onDelete,
  onCancel,
  summaryError,
}) => {
  if (summaryError) {
    return (
      <Modal
        title={<span style={{ color: 'var(--text-main)' }}>Delete Datasource</span>}
        open={open}
        onCancel={onCancel}
        footer={[
          <Button key="back" onClick={onCancel}>
            Close
          </Button>,
        ]}
        width={700}
        style={{ top: 30 }}
        styles={{ body: { backgroundColor: 'var(--bg-card)' } }}
      >
        <Alert
          message="Failed to Load Summary"
          description={summaryError}
          type="error"
          showIcon
          style={{ margin: '2rem 0' }}
        />
      </Modal>
    );
  }

  // Graceful fallback if data isn't loaded yet
  if (!deleteSummary || !deleteSummary.connection || !deleteSummary.summary) {
    return (
      <Modal
        title={<span style={{ color: 'var(--text-main)' }}>Delete Datasource</span>}
        open={open}
        onCancel={onCancel}
        footer={null}
        width={700}
        style={{ top: 30 }}
        styles={{ body: { backgroundColor: 'var(--bg-card)' } }}
      >
        <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-secondary)' }}>
          Loading summary data...
        </div>
      </Modal>
    );
  }

  const { connection, summary } = deleteSummary;

  // Configuration for items that will be deleted
  const deletionImpactItems = [
    { label: 'Schema Tables', count: summary.schema_tables },
    { label: 'Schema Columns', count: summary.schema_columns },
    { label: 'Relationships', count: summary.schema_relationships },
    { label: 'Column Display Config', count: summary.column_display },
    { label: 'Schema Drift Events', count: summary.schema_drift_events },
    { label: 'Semantic Dimensions', count: summary.semantic_dimensions },
    { label: 'Semantic Metrics', count: summary.semantic_metrics },
    { label: 'Semantic Relationships', count: summary.semantic_relationships },
  ];

  return (
    <Modal
      title={
        <Text strong style={{ fontSize: '16px', color: 'var(--text-main)' }}>
          Delete Datasource
        </Text>
      }
      open={open}
      onCancel={onCancel}
      width={700}
      centered
      keyboard={true}
      maskClosable={false}
      style={{ top: 30 }}
      styles={{
        body: {
          backgroundColor: 'var(--bg-card)',
          maxHeight: '75vh',
          overflowY: 'auto',
          padding: '16px 24px'
        }
      }}
      footer={[
        <Button key="back" onClick={onCancel} disabled={loading}>
          Cancel
        </Button>,
        <Button
          key="submit"
          type="primary"
          danger
          loading={loading}
          onClick={onDelete}
          disabled={confirmText !== connection.connection_name}
        >
          Delete Datasource
        </Button>,
      ]}
    >
      <Space direction="vertical" size="large" style={{ width: '100%', marginTop: '8px' }}>
        
        {/* Section 1: Datasource Information */}
        <Card 
          size="small" 
          title={<span style={{ color: 'var(--text-main)', fontWeight: 600 }}>Datasource Information</span>} 
          style={{
            borderRadius: '8px',
            backgroundColor: 'var(--bg-card-inner)',
            borderColor: 'var(--border-color)'
          }}
        >
          <Descriptions column={2} size="small">
            <Descriptions.Item label={<span style={{ color: 'var(--text-muted)' }}>Name</span>}>
              <Text strong style={{ color: 'var(--text-main)' }}>{connection.connection_name}</Text>
            </Descriptions.Item>
            <Descriptions.Item label={<span style={{ color: 'var(--text-muted)' }}>Database Type</span>}>
              <Text style={{ color: 'var(--text-secondary)' }}>{connection.database_type}</Text>
            </Descriptions.Item>
            <Descriptions.Item label={<span style={{ color: 'var(--text-muted)' }}>Database</span>}>
              <Text style={{ color: 'var(--text-secondary)' }}>{connection.database_name || 'N/A'}</Text>
            </Descriptions.Item>
            <Descriptions.Item label={<span style={{ color: 'var(--text-muted)' }}>Host</span>}>
              <Text style={{ color: 'var(--text-secondary)' }}>{connection.host}</Text>
            </Descriptions.Item>
            <Descriptions.Item label={<span style={{ color: 'var(--text-muted)' }}>Status</span>}>
              <Badge 
                status={connection.connection_status === 'ACTIVE' ? 'success' : 'default'} 
                text={<span style={{ color: 'var(--text-secondary)' }}>{connection.connection_status}</span>} 
              />
            </Descriptions.Item>
          </Descriptions>
        </Card>

        {/* Section 2: Deletion Impact */}
        <Card 
          size="small" 
          title={<span style={{ color: '#ef4444', fontWeight: 600 }}>Items that will be permanently removed</span>} 
          style={{
            borderRadius: '8px',
            borderColor: 'rgba(239, 68, 68, 0.4)',
            backgroundColor: 'rgba(239, 68, 68, 0.08)'
          }}
        >
          <List
            size="small"
            dataSource={deletionImpactItems}
            split={false}
            renderItem={(item) => (
              <List.Item style={{ padding: '4px 0' }}>
                <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space>
                    <CheckOutlined style={{ color: '#ef4444' }} />
                    <Text style={{ color: 'var(--text-main)' }}>{item.label}</Text>
                  </Space>
                  <Badge
                    count={item.count}
                    showZero
                    style={{
                      backgroundColor: 'rgba(239, 68, 68, 0.2)',
                      color: '#f87171',
                      borderColor: 'rgba(239, 68, 68, 0.4)',
                      fontWeight: 600
                    }}
                  />
                </Space>
              </List.Item>
            )}
          />
        </Card>

        {/* Section 3: Audit Preservation */}
        <Card 
          size="small" 
          title={<span style={{ color: '#10b981', fontWeight: 600 }}>Items that will be preserved</span>} 
          style={{
            borderRadius: '8px',
            borderColor: 'rgba(16, 185, 129, 0.4)',
            backgroundColor: 'rgba(16, 185, 129, 0.08)'
          }}
        >
          <List
            size="small"
            dataSource={[{ label: 'Lifecycle Audit Events', count: summary.lifecycle_events }]}
            split={false}
            renderItem={(item) => (
              <List.Item style={{ padding: '4px 0' }}>
                <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space>
                    <SafetyCertificateOutlined style={{ color: '#10b981' }} />
                    <Text strong style={{ color: 'var(--text-main)' }}>{item.label}</Text>
                  </Space>
                  <Badge
                    count={item.count}
                    showZero
                    style={{
                      backgroundColor: 'rgba(16, 185, 129, 0.2)',
                      color: '#34d399',
                      borderColor: 'rgba(16, 185, 129, 0.4)',
                      fontWeight: 600
                    }}
                  />
                </Space>
              </List.Item>
            )}
          />
          <div style={{ marginTop: '8px' }}>
            <Text style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Lifecycle history is retained permanently for auditing and compliance.
            </Text>
          </div>
        </Card>

        {/* Section 4: Danger Warning */}
        <Alert
          type="warning"
          showIcon
          message={
            <Text strong style={{ color: 'var(--text-main)' }}>
              Deleting this datasource permanently removes all synchronized metadata and semantic configurations.
            </Text>
          }
          description={<span style={{ color: 'var(--text-secondary)' }}>This action cannot be undone.</span>}
          style={{ borderRadius: '8px' }}
        />

        {/* Section 5: Confirmation */}
        <div style={{ padding: '8px 0' }}>
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            <Text style={{ color: 'var(--text-main)' }}>
              To confirm deletion, type the datasource name exactly: <b style={{ color: '#ef4444' }}>{connection.connection_name}</b>
            </Text>
            <Input
              placeholder="Enter datasource name"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              onPressEnter={() => {
                if (confirmText === connection.connection_name) {
                  onDelete();
                }
              }}
              autoComplete="off"
              size="large"
            />
          </Space>
        </div>

      </Space>
    </Modal>
  );
};

export default DeleteDatasourceModal;
