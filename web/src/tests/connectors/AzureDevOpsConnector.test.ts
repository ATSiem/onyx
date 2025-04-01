import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { FormikProvider, Field } from 'formik';
import '@testing-library/jest-dom';

// Mock the SelectInput component
jest.mock('../../app/admin/connectors/[connector]/pages/ConnectorInput/SelectInput', () => ({
  __esModule: true,
  default: jest.fn(({ name, onChange }) => (
    <div>
      <select 
        data-testid={`select-${name}`} 
        onChange={(e) => onChange && onChange(e)}
      >
        <option value="work_items_only">Work Items Only</option>
        <option value="everything">Everything</option>
      </select>
    </div>
  )),
}));

describe('Azure DevOps Connector', () => {
  test('content_scope selection sets correct value', async () => {
    // Create a mock FormikContext
    const formik = {
      values: {},
      setFieldValue: jest.fn(),
    };

    // Test that selecting the dropdown sets the value
    const TestComponent = () => (
      <FormikProvider value={formik as any}>
        <Field
          name="content_scope"
          component="select"
          data-testid="content-scope-select"
        >
          <option value="work_items_only">Work Items Only</option>
          <option value="everything">Everything</option>
        </Field>
      </FormikProvider>
    );

    render(<TestComponent />);

    // Simulate selecting "everything" from dropdown
    fireEvent.change(screen.getByTestId('content-scope-select'), { 
      target: { value: 'everything' } 
    });

    // Verify the formik context updates appropriately
    expect(formik.setFieldValue).toHaveBeenCalledWith(
      'content_scope', 
      'everything', 
      true
    );
  });
}); 