import React, { useState } from 'react';
import { Button, Form, Input, Switch, Select, Card, Typography, Space, Alert, Spin } from 'antd';
import { GoogleOutlined, SettingOutlined, UserOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;
const { Option } = Select;

interface GoogleSignupData {
  first_name: string;
  last_name: string;
  username: string;
  password: string;
  phone_number?: string;
  recovery_email?: string;
  birth_date?: string;
  gender?: string;
  skip_phone_verification: boolean;
}

interface GoogleSignupConfig {
  headless: boolean;
  timeout: number;
  retry_attempts: number;
  use_mobile_user_agent: boolean;
  prefer_phone_verification: boolean;
  auto_handle_captcha: boolean;
}

interface GoogleSignupFormProps {
  onSignup: (identityId?: number, manualData?: GoogleSignupData, config?: GoogleSignupConfig) => Promise<void>;
  loading?: boolean;
  identities?: Array<{ id: number; name: string; description?: string }>;
}

const GoogleSignupForm: React.FC<GoogleSignupFormProps> = ({ onSignup, loading = false, identities = [] }) => {
  const [form] = Form.useForm();
  const [signupMode, setSignupMode] = useState<'identity' | 'manual'>('identity');
  const [selectedIdentity, setSelectedIdentity] = useState<number | undefined>();
  const [config, setConfig] = useState<GoogleSignupConfig>({
    headless: true,
    timeout: 120,
    retry_attempts: 3,
    use_mobile_user_agent: false,
    prefer_phone_verification: true,
    auto_handle_captcha: false,
  });
  const [showAdvancedConfig, setShowAdvancedConfig] = useState(false);

  const handleSubmit = async (values: any) => {
    try {
      if (signupMode === 'identity' && selectedIdentity) {
        await onSignup(selectedIdentity, undefined, config);
      } else if (signupMode === 'manual') {
        const manualData: GoogleSignupData = {
          first_name: values.first_name,
          last_name: values.last_name,
          username: values.username,
          password: values.password,
          phone_number: values.phone_number,
          recovery_email: values.recovery_email,
          birth_date: values.birth_date,
          gender: values.gender,
          skip_phone_verification: values.skip_phone_verification || false,
        };
        await onSignup(undefined, manualData, config);
      }
    } catch (error) {
      console.error('Signup error:', error);
    }
  };

  const handleConfigChange = (key: keyof GoogleSignupConfig, value: any) => {
    setConfig(prev => ({ ...prev, [key]: value }));
  };

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '24px' }}>
      <Card>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div style={{ textAlign: 'center' }}>
            <GoogleOutlined style={{ fontSize: '48px', color: '#1890ff', marginBottom: '16px' }} />
            <Title level={2}>Google Account Signup</Title>
            <Text type="secondary">
              Automate Google account creation using your identities or manual data
            </Text>
          </div>

          {/* Signup Mode Selection */}
          <Card size="small" title="Signup Mode">
            <Space>
              <Button
                type={signupMode === 'identity' ? 'primary' : 'default'}
                icon={<UserOutlined />}
                onClick={() => setSignupMode('identity')}
              >
                Use Identity
              </Button>
              <Button
                type={signupMode === 'manual' ? 'primary' : 'default'}
                onClick={() => setSignupMode('manual')}
              >
                Manual Data
              </Button>
            </Space>
          </Card>

          <Form
            form={form}
            layout="vertical"
            onFinish={handleSubmit}
          >
            {signupMode === 'identity' ? (
              <Card size="small" title="Select Identity">
                <Form.Item
                  name="identity_id"
                  label="Identity"
                  rules={[{ required: true, message: 'Please select an identity' }]}
                >
                  <Select
                    placeholder="Select an identity to use for signup"
                    value={selectedIdentity}
                    onChange={setSelectedIdentity}
                  >
                    {identities.map(identity => (
                      <Option key={identity.id} value={identity.id}>
                        <div>
                          <div style={{ fontWeight: 'bold' }}>{identity.name}</div>
                          {identity.description && (
                            <div style={{ fontSize: '12px', color: '#666' }}>
                              {identity.description}
                            </div>
                          )}
                        </div>
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              </Card>
            ) : (
              <Card size="small" title="Manual Signup Data">
                <Form.Item
                  name="first_name"
                  label="First Name"
                  rules={[{ required: true, message: 'First name is required' }]}
                >
                  <Input placeholder="Enter first name" />
                </Form.Item>

                <Form.Item
                  name="last_name"
                  label="Last Name"
                  rules={[{ required: true, message: 'Last name is required' }]}
                >
                  <Input placeholder="Enter last name" />
                </Form.Item>

                <Form.Item
                  name="username"
                  label="Desired Username"
                  rules={[
                    { required: true, message: 'Username is required' },
                    { min: 6, message: 'Username must be at least 6 characters' },
                    { max: 30, message: 'Username must be at most 30 characters' }
                  ]}
                >
                  <Input placeholder="Enter desired username (6-30 characters)" />
                </Form.Item>

                <Form.Item
                  name="password"
                  label="Password"
                  rules={[
                    { required: true, message: 'Password is required' },
                    { min: 8, message: 'Password must be at least 8 characters' }
                  ]}
                >
                  <Input.Password placeholder="Enter password (min 8 characters)" />
                </Form.Item>

                <Form.Item
                  name="phone_number"
                  label="Phone Number (Optional)"
                  help="For account recovery and verification"
                >
                  <Input placeholder="+1234567890" />
                </Form.Item>

                <Form.Item
                  name="recovery_email"
                  label="Recovery Email (Optional)"
                >
                  <Input type="email" placeholder="recovery@example.com" />
                </Form.Item>

                <Form.Item
                  name="birth_date"
                  label="Birth Date (Optional)"
                  help="Format: YYYY-MM-DD"
                >
                  <Input placeholder="1990-01-01" />
                </Form.Item>

                <Form.Item
                  name="gender"
                  label="Gender (Optional)"
                >
                  <Select placeholder="Select gender">
                    <Option value="male">Male</Option>
                    <Option value="female">Female</Option>
                    <Option value="other">Other</Option>
                    <Option value="prefer_not_to_say">Prefer not to say</Option>
                  </Select>
                </Form.Item>

                <Form.Item
                  name="skip_phone_verification"
                  valuePropName="checked"
                >
                  <Switch /> Skip phone verification (if possible)
                </Form.Item>
              </Card>
            )}

            {/* Advanced Configuration */}
            <Card size="small" title="Configuration">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Button
                  type="link"
                  icon={<SettingOutlined />}
                  onClick={() => setShowAdvancedConfig(!showAdvancedConfig)}
                >
                  {showAdvancedConfig ? 'Hide' : 'Show'} Advanced Settings
                </Button>

                {showAdvancedConfig && (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <div>
                      <Text strong>Headless Mode:</Text>
                      <Switch
                        checked={config.headless}
                        onChange={(checked) => handleConfigChange('headless', checked)}
                        style={{ marginLeft: 8 }}
                      />
                      <div style={{ fontSize: '12px', color: '#666' }}>
                        Run browser in background (recommended)
                      </div>
                    </div>

                    <div>
                      <Text strong>Timeout (seconds):</Text>
                      <Input
                        type="number"
                        value={config.timeout}
                        onChange={(e) => handleConfigChange('timeout', parseInt(e.target.value))}
                        style={{ width: 100, marginLeft: 8 }}
                        min={30}
                        max={300}
                      />
                    </div>

                    <div>
                      <Text strong>Retry Attempts:</Text>
                      <Input
                        type="number"
                        value={config.retry_attempts}
                        onChange={(e) => handleConfigChange('retry_attempts', parseInt(e.target.value))}
                        style={{ width: 100, marginLeft: 8 }}
                        min={1}
                        max={5}
                      />
                    </div>

                    <div>
                      <Text strong>Mobile User Agent:</Text>
                      <Switch
                        checked={config.use_mobile_user_agent}
                        onChange={(checked) => handleConfigChange('use_mobile_user_agent', checked)}
                        style={{ marginLeft: 8 }}
                      />
                      <div style={{ fontSize: '12px', color: '#666' }}>
                        Use mobile browser simulation
                      </div>
                    </div>

                    <div>
                      <Text strong>Prefer Phone Verification:</Text>
                      <Switch
                        checked={config.prefer_phone_verification}
                        onChange={(checked) => handleConfigChange('prefer_phone_verification', checked)}
                        style={{ marginLeft: 8 }}
                      />
                    </div>

                    <div>
                      <Text strong>Auto Handle CAPTCHA:</Text>
                      <Switch
                        checked={config.auto_handle_captcha}
                        onChange={(checked) => handleConfigChange('auto_handle_captcha', checked)}
                        style={{ marginLeft: 8 }}
                      />
                      <div style={{ fontSize: '12px', color: '#666' }}>
                        Attempt automatic CAPTCHA solving
                      </div>
                    </div>
                  </Space>
                )}
              </Space>
            </Card>

            <Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                size="large"
                icon={<GoogleOutlined />}
                block
              >
                {loading ? 'Creating Account...' : 'Create Google Account'}
              </Button>
            </Form.Item>
          </Form>
        </Space>
      </Card>
    </div>
  );
};

export default GoogleSignupForm; 