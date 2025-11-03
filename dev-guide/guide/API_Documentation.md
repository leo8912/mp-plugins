# API 文档

本文档详细介绍了 Tmdb Storyliner 插件/应用程序使用的所有 API 接口。

## 1. TMDB API

[TMDB (The Movie Database)](https://www.themoviedb.org/) 是一个社区维护的电影和电视剧数据库，提供丰富的元数据信息。

### 1.1 基础信息

- **API文档**: https://developers.themoviedb.org/
- **API版本**: v3
- **基础URL**: https://api.themoviedb.org/3
- **认证方式**: API密钥（通过查询参数传递）

### 1.2 API密钥获取

1. 访问 [TMDB官网](https://www.themoviedb.org/) 并注册账号
2. 登录后访问 [API设置页面](https://www.themoviedb.org/settings/api)
3. 申请API密钥

### 1.3 使用的API接口

#### 1.3.1 获取电影详情

**接口地址**: `/movie/{movie_id}`

**请求方式**: GET

**请求参数**:
- `api_key` (必需) - 您的TMDB API密钥
- `language` (可选) - 语言代码，例如 `en-US`

**示例请求**:
```
GET https://api.themoviedb.org/3/movie/550?api_key=YOUR_API_KEY&language=en-US
```

**响应字段**:
```json
{
  "adult": false,
  "backdrop_path": "/fCayJrkfRaCRCTh8GqN30f8oyQF.jpg",
  "belongs_to_collection": null,
  "budget": 63000000,
  "genres": [
    {
      "id": 18,
      "name": "Drama"
    }
  ],
  "homepage": "",
  "id": 550,
  "imdb_id": "tt0137523",
  "original_language": "en",
  "original_title": "Fight Club",
  "overview": "A ticking-time-bomb insomniac and a slippery soap salesman channel primal male aggression into a shocking new form of therapy. Their concept catches on, with underground \"fight clubs\" forming in every town, until an eccentric gets in the way and ignites an out-of-control spiral toward oblivion.",
  "popularity": 36.266,
  "poster_path": "/adMKGjHgyv8kCFjO7B9ERzUl7En.jpg",
  "production_companies": [...],
  "production_countries": [...],
  "release_date": "1999-10-15",
  "revenue": 100853753,
  "runtime": 139,
  "spoken_languages": [...],
  "status": "Released",
  "tagline": "Mischief. Mayhem. Soap.",
  "title": "Fight Club",
  "video": false,
  "vote_average": 8.4,
  "vote_count": 20080
}
```

**插件中使用场景**:
- 获取电影的剧情简介 (`overview` 字段)
- 获取电影的原始语言 (`original_language` 字段)
- 获取电影的其他元数据信息

#### 1.3.2 获取电视剧详情

**接口地址**: `/tv/{series_id}`

**请求方式**: GET

**请求参数**:
- `api_key` (必需) - 您的TMDB API密钥
- `language` (可选) - 语言代码，例如 `en-US`

**示例请求**:
```
GET https://api.themoviedb.org/3/tv/1396?api_key=YOUR_API_KEY&language=en-US
```

**响应字段**:
```json
{
  "backdrop_path": "/tsRy63Mu5cu8etL1X7ZLyf7UP1M.jpg",
  "created_by": [...],
  "episode_run_time": [45],
  "first_air_date": "2008-01-20",
  "genres": [...],
  "homepage": "http://www.amctv.com/shows/breaking-bad",
  "id": 1396,
  "in_production": false,
  "languages": ["en"],
  "last_air_date": "2013-09-29",
  "last_episode_to_air": {...},
  "name": "Breaking Bad",
  "next_episode_to_air": null,
  "networks": [...],
  "number_of_episodes": 62,
  "number_of_seasons": 5,
  "origin_country": ["US"],
  "original_language": "en",
  "original_name": "Breaking Bad",
  "overview": "When Walter White, a New Mexico chemistry teacher, is diagnosed with Stage III cancer and given a prognosis of only two years left to live. He becomes filled with a sense of fearlessness and an unrelenting desire to secure his family's financial future at any cost as he enters the dangerous world of drugs and crime.",
  "popularity": 209.056,
  "poster_path": "/1yeVJox3rjo2jBKrrihIMj7uoS9.jpg",
  "production_companies": [...],
  "production_countries": [...],
  "seasons": [...],
  "status": "Ended",
  "type": "Scripted",
  "vote_average": 8.9,
  "vote_count": 7088
}
```

**插件中使用场景**:
- 获取电视剧的剧情简介 (`overview` 字段)
- 获取电视剧的原始语言 (`original_language` 字段)
- 获取电视剧的其他元数据信息

#### 1.3.3 获取剧集详情

**接口地址**: `/tv/{series_id}/season/{season_number}/episode/{episode_number}`

**请求方式**: GET

**请求参数**:
- `api_key` (必需) - 您的TMDB API密钥
- `language` (可选) - 语言代码，例如 `en-US`

**示例请求**:
```
GET https://api.themoviedb.org/3/tv/1396/season/1/episode/1?api_key=YOUR_API_KEY&language=en-US
```

**响应字段**:
```json
{
  "air_date": "2008-01-20",
  "crew": [...],
  "episode_number": 1,
  "guest_stars": [...],
  "name": "Pilot",
  "overview": "When an unassuming high school chemistry teacher discovers he has a rare form of lung cancer, he decides to team up with a former student and create a new identity to provide for his family's future.",
  "id": 62085,
  "production_code": "",
  "runtime": 58,
  "season_number": 1,
  "still_path": "/cwqUAsWjxC73wg10c1c9ksReC1x.jpg",
  "vote_average": 8.1,
  "vote_count": 160
}
```

**插件中使用场景**:
- 获取剧集的剧情简介 (`overview` 字段)
- 获取剧集的其他元数据信息

## 2. 翻译服务 API

### 2.1 百度翻译 API

[百度翻译开放平台](https://fanyi-api.baidu.com/) 提供多种语言的文本翻译服务。

#### 2.1.1 基础信息

- **API文档**: https://api.fanyi.baidu.com/doc/21
- **基础URL**: https://fanyi-api.baidu.com/api/trans/vip/translate
- **认证方式**: APP ID + 密钥签名

#### 2.1.2 API密钥获取

1. 访问 [百度翻译开放平台](https://fanyi-api.baidu.com/)
2. 注册账号并登录
3. 创建应用获取 APP ID 和密钥

#### 2.1.3 文本翻译接口

**接口地址**: `/api/trans/vip/translate`

**请求方式**: GET/POST

**请求参数**:
- `q` (必需) - 请求翻译 query
- `from` (必需) - 源语言
- `to` (必需) - 目标语言
- `appid` (必需) - APP ID
- `salt` (必需) - 随机数
- `sign` (必需) - 签名

**签名生成方法**:
```
sign = MD5(appid + q + salt + 密钥)
```

**示例请求**:
```
GET https://fanyi-api.baidu.com/api/trans/vip/translate?q=hello&from=en&to=zh&appid=2015063000000001&salt=1435660288&sign=f6f050dc080151087487197435131409
```

**响应示例**:
```json
{
  "from": "en",
  "to": "zh",
  "trans_result": [
    {
      "src": "hello",
      "dst": "你好"
    }
  ]
}
```

**插件中使用场景**:
- 将英文剧情简介翻译为中文
- 语言检测（通过翻译结果判断）

### 2.2 腾讯云翻译 API

[腾讯云机器翻译](https://cloud.tencent.com/product/tmt) 提供高质量的机器翻译服务。

#### 2.2.1 基础信息

- **API文档**: https://cloud.tencent.com/document/product/551
- **基础URL**: https://tmt.tencentcloudapi.com
- **认证方式**: SecretId + SecretKey 签名

#### 2.2.2 API密钥获取

1. 访问 [腾讯云官网](https://cloud.tencent.com/) 并注册账号
2. 进入控制台，开通机器翻译服务
3. 创建密钥获取 SecretId 和 SecretKey

#### 2.2.3 文本翻译接口

**接口地址**: `/`

**请求方式**: POST

**请求参数** (通过请求头传递):
- `Authorization` - 签名信息
- `Content-Type` - application/json; charset=utf-8
- `X-TC-Action` - TextTranslate
- `X-TC-Version` - 2018-03-21
- `X-TC-Region` - ap-beijing

**请求体**:
```json
{
  "SourceText": "Hello World",
  "Source": "en",
  "Target": "zh",
  "ProjectId": 0
}
```

**响应示例**:
```json
{
  "Response": {
    "TargetText": "你好世界",
    "Source": "en",
    "Target": "zh",
    "RequestId": "RequestId"
  }
}
```

**插件中使用场景**:
- 将英文剧情简介翻译为中文
- 支持多种语言翻译

### 2.3 阿里云翻译 API

[阿里云机器翻译](https://www.aliyun.com/product/ai/alimt) 提供多语言翻译服务。

#### 2.3.1 基础信息

- **API文档**: https://help.aliyun.com/document_detail/158296.html
- **基础URL**: https://mt.cn-hangzhou.aliyuncs.com
- **认证方式**: AccessKey ID + AccessKey Secret 签名

#### 2.3.2 API密钥获取

1. 访问 [阿里云官网](https://www.aliyun.com/) 并注册账号
2. 进入控制台，开通机器翻译服务
3. 创建访问密钥获取 AccessKey ID 和 AccessKey Secret

#### 2.3.3 文本翻译接口

**接口地址**: `/`
**请求方式**: POST
**协议**: HTTPS

**请求参数** (通过请求头传递):
- `Authorization` - 签名信息
- `Content-Type` - application/json; charset=utf-8
- `X-ACS-Action` - TranslateECommerce
- `X-ACS-Version` - 2019-01-07
- `X-ACS-Date` - 请求时间
- `X-ACS-Region-Id` - cn-hangzhou

**请求体**:
```json
{
  "FormatType": "text",
  "SourceLanguage": "en",
  "TargetLanguage": "zh",
  "SourceText": "Hello World",
  "Scene": "general"
}
```

**响应示例**:
```json
{
  "RequestId": "RequestId",
  "Data": {
    "Translated": "你好世界",
    "Code": "200"
  }
}
```

**插件中使用场景**:
- 将英文剧情简介翻译为中文
- 支持电商场景的翻译

## 3. Emby API

[Emby](https://emby.media/) 是一个个人媒体服务器，提供丰富的 REST API 接口。

### 3.1 基础信息

- **API文档**: 通过 Emby 服务器访问 `/emby/swagger` 查看
- **基础URL**: `http://your-emby-server:port/emby`
- **认证方式**: API Key (通过查询参数或请求头传递)

### 3.2 API密钥获取

1. 登录 Emby 管理界面
2. 进入 "Dashboard" -> "Advanced" -> "Security"
3. 在 "API Keys" 部分创建新的 API 密钥

### 3.3 使用的API接口

#### 3.3.1 获取媒体库项目

**接口地址**: `/Items`

**请求方式**: GET

**请求参数**:
- `api_key` (必需) - Emby API 密钥
- `Recursive` (可选) - 是否递归获取子项目
- `IncludeItemTypes` (可选) - 包含的项目类型，如 Movie, Series, Episode
- `Fields` (可选) - 需要返回的额外字段，如 ProviderIds

**示例请求**:
```
GET http://localhost:8096/emby/Items?Recursive=true&IncludeItemTypes=Movie&Fields=ProviderIds,Overview&api_key=YOUR_API_KEY
```

**响应示例**:
```json
{
  "Items": [
    {
      "Name": "Fight Club",
      "ServerId": "1234567890abcdef1234567890abcdef12345678",
      "Id": "5de4b0b5b9941c15c05831b1",
      "Overview": "A ticking-time-bomb insomniac and a slippery soap salesman channel primal male aggression into a shocking new form of therapy.",
      "ProviderIds": {
        "Tmdb": "550",
        "Imdb": "tt0137523"
      },
      "Type": "Movie",
      // ... 其他字段
    }
  ],
  "TotalRecordCount": 1,
  "StartIndex": 0
}
```

**插件中使用场景**:
- 获取需要更新剧情简介的媒体项目
- 获取项目的 TMDB ID 用于查询 TMDB API
- 获取项目当前的剧情简介

#### 3.3.2 更新媒体项目

**接口地址**: `/Items/{itemId}`

**请求方式**: POST

**请求参数**:
- `api_key` (必需) - Emby API 密钥
- `itemId` (必需) - 要更新的项目 ID

**请求体**:
```json
{
  "Id": "itemId",
  "Overview": "更新后的剧情简介"
}
```

**示例请求**:
```
POST http://localhost:8096/emby/Items/5de4b0b5b9941c15c05831b1?api_key=YOUR_API_KEY
Content-Type: application/json

{
  "Id": "5de4b0b5b9941c15c05831b1",
  "Overview": "更新后的剧情简介内容"
}
```

**响应**:
- 成功时返回 204 No Content
- 失败时返回相应错误码

**插件中使用场景**:
- 更新媒体项目的剧情简介
- 更新其他元数据信息

## 4. 总结

本插件/应用程序集成了以下API服务：

1. **TMDB API** - 获取电影、电视剧和剧集的原始剧情简介
2. **翻译服务API** - 将英文剧情简介翻译为中文
   - 百度翻译
   - 腾讯云翻译
   - 阿里云翻译
3. **Emby API** - 与Emby服务器交互，获取项目信息并更新剧情简介

所有这些API都通过HTTPS协议进行安全通信，并且需要相应的API密钥进行认证。插件通过合理使用这些API，实现了自动获取和更新媒体项目剧情简介的功能。