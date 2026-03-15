fulltext_css = '''
<style>
    .paper-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        margin-bottom: 30px;
    }
    .paper-card-s {
        background-color: #ffffff;
        padding: 10px;
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        margin-bottom: 10px;
    }
    .title {
        color:rgb(26, 25, 25);
        font-size: 24px;
        font-weight: bold;
        margin-bottom: 15px;
    }
    .authors {
        color: #333333;
        font-size: 15px;
        margin-bottom: 15px;
    }
    .metadata {
        margin-bottom: 15px;
        font-size: 14px;
        color: #666666;
        line-height: 1.5;
    }
    .metadata-item {
        margin-right: 15px;
    }
    .score-badge {
        background-color: #f8f9fa;
        color: #555;
        padding: 3px 8px;
        border-radius: 12px;
        font-size: 13px;
    }
    .section-title {
        color:rgb(48, 105, 129);
        font-size: 20px;
        margin-top: 20px;
        margin-bottom: 10px;
        border-left: 4px solid #6c757d;
        padding-left: 10px;
    }
    .content {
        font-size: 15px;
        line-height: 1.6;
        color:rgb(31, 31, 31);
    }
    img {
        border: 1px solid #ddd;
        border-radius: 4px;
        padding: 5px;
        margin: 10px 0;
        max-width: 100%;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        transition: transform 0.3s ease;
    }
    img:hover {
        transform: scale(1.2);
    }
    table {
        width: 90%;
        border-collapse: collapse;
        margin: 15px 0;
    }
    th, td {
        border: 1px solid #ddd;
        padding: 8px;
        text-align: left;
    }
    th {
        background-color: #f2f2f2;
        font-weight: bold;
    }
    .figure-gallery {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 15px;
        margin: 20px 0;
    }

    .figure-gallery img {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 6px;
        padding: 8px;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }

    .figure-gallery img:hover {
        transform: scale(1.2);
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.15);
    }

    .figure-gallery figcaption {
        text-align: center;
        margin-top: 8px;
        font-size: 14px;
        color: #6c757d;
    }

    .table-container {
        overflow-x: auto;
        margin: 20px 0;
        background-color: #f8f9fa;
        border-radius: 6px;
        border: 1px solid #e9ecef;
        padding: 15px;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
    }
    .highlight {
        background-color: #f8f9fa;
        padding: 2px 5px;
        border-radius: 3px;
    }
    @media (max-width: 600px) {
        .title {
            font-size: 20px;
        }
        .content {
            font-size: 14px;
        }
    }
</style>
'''