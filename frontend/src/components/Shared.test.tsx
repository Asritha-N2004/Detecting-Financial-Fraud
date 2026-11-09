import {render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {describe,it,expect} from 'vitest';
import {Badge,Empty,ErrorBox,number} from './Shared';
describe('evidence availability and status',()=>{
 it('never renders missing risk as zero',()=>{expect(number(null)).toBe('Unavailable');expect(number(0)).toBe('0')});
 it('displays explicit failure and warning labels',()=>{render(<><Badge value="completed_with_warnings"/><Badge value="failed"/></>);expect(screen.getByText('completed with warnings')).toBeInTheDocument();expect(screen.getByText('failed')).toBeInTheDocument()});
 it('shows a useful empty state with assessment action',()=>{render(<MemoryRouter><Empty title="Select an assessment" description="Supply evidence first"/></MemoryRouter>);expect(screen.getByRole('link')).toHaveAttribute('href','/new')});
 it('exposes request errors accessibly',()=>{render(<ErrorBox message="Insufficient evidence"/>);expect(screen.getByRole('alert')).toHaveTextContent('Insufficient evidence')});
});
