/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'export',
  images: {
    unoptimized: true,
  },
  trailingSlash: true,
  
  // Thêm cấu hình này
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Access-Control-Allow-Origin',
            value: '*', // Hoặc chỉ định domain chính xác
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;