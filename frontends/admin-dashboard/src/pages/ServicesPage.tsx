import React from 'react';
import { Container, Typography, Paper, Box } from '@mui/material';

const ServicesPage: React.FC = () => {
  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        Service Health
      </Typography>
      <Paper sx={{ p: 4, height: 600 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          <Typography variant="h6" color="text.secondary">
            Service health monitoring will be implemented here
          </Typography>
        </Box>
      </Paper>
    </Container>
  );
};

export default ServicesPage;